import logging
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from .analysis import AnalysisRequest, AnalysisResult, Outcome, Source, Stages, run_analysis
from .aoi import InvalidAoi
from .pipeline.pairing import Rejection
from .pipeline.raster import GridError, Parameters, RenderedLayers
from .providers.base import ProviderError, SarProvider

Status = Literal["queued", "running", "done", "failed", "no_comparable_pair"]
logger = logging.getLogger(__name__)


class Snapshot(BaseModel):
    id: str
    source: Source
    status: Status
    stage: Stages | None = None
    message: str | None = None
    code: str | None = None
    result: AnalysisResult | None = None
    rejections: tuple[Rejection, ...] = ()


@dataclass
class Record:
    snapshot: Snapshot
    started: float
    active: bool = True
    layers: RenderedLayers | None = None


class QueueFull(RuntimeError):
    pass


class JobExpired(RuntimeError):
    pass


class Jobs:
    def __init__(self):
        self._records: dict[str, Record] = {}
        self._lock = Lock()
        self._timeout = 150

    def create(self, source: Source) -> Snapshot:
        with self._lock:
            now = monotonic()
            for key in list(self._records):
                record = self._records[key]
                if not record.active and now - record.started > 3600:
                    del self._records[key]
            if sum(record.active for record in self._records.values()) >= 2:
                raise QueueFull("Two analyses are in progress. Try again shortly.")
            if len(self._records) >= 24:
                oldest = next(key for key, record in self._records.items() if not record.active)
                del self._records[oldest]
            job = Snapshot(id=uuid4().hex, source=source, status="queued")
            self._records[job.id] = Record(job, now)
            return job

    def _expire(self, record: Record) -> bool:
        if record.active and monotonic() - record.started > self._timeout:
            record.snapshot = record.snapshot.model_copy(update={
                "status": "failed", "stage": None, "code": "TIMED_OUT",
                "message": "The analysis timed out. Try a smaller area or shorter observation window.",
            })
            return True
        return False

    def get(self, job_id: str) -> tuple[Snapshot, RenderedLayers | None] | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or (not record.active and monotonic() - record.started > 3600):
                return None
            self._expire(record)
            return record.snapshot, record.layers

    def _progress(self, job_id: str, stage: Stages) -> None:
        with self._lock:
            record = self._records[job_id]
            if self._expire(record):
                raise JobExpired
            record.snapshot = record.snapshot.model_copy(update={"status": "running", "stage": stage})

    def _finish(self, job_id: str, outcome: Outcome | None, error: tuple[str, str] | None) -> None:
        with self._lock:
            record = self._records[job_id]
            expired = self._expire(record)
            record.active = False
            if expired:
                return
            if error:
                reply = {"status": "failed", "code": error[0], "message": error[1]}
            elif outcome and outcome.result is not None:
                reply = {"status": "done", "result": outcome.result, "rejections": outcome.rejections}
                record.layers = outcome.layers
            else:
                reply = {"status": "no_comparable_pair", "code": "NO_COMPARABLE_PAIR",
                         "message": "No comparable pair was found. Try a wider window or a smaller study area.",
                         "rejections": outcome.rejections if outcome else ()}
            record.snapshot = record.snapshot.model_copy(update={"stage": None, **reply})

    def run(self, job_id: str, request: AnalysisRequest, provider: SarProvider, params: Parameters, limit: float) -> None:
        outcome = None
        failure = None
        try:
            outcome = run_analysis(job_id, request, provider, params, limit, lambda stage: self._progress(job_id, stage))
        except JobExpired:
            pass
        except (GridError, InvalidAoi) as error:
            failure = ("INVALID_AREA", str(error))
        except ProviderError as error:
            failure = ("PROVIDER_UNAVAILABLE", str(error))
        except Exception as error:
            logger.error("Analysis %s failed with %s", job_id, type(error).__name__)
            failure = ("ANALYSIS_FAILED", "The analysis could not complete. Try again with a smaller area or different date.")
        finally:
            self._finish(job_id, outcome, failure)
