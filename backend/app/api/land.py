import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import TypeVar

import numpy as np
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from PIL import Image
from pydantic import BaseModel

from ..config import Settings
from ..land import LandBundle, LandProfile, LandRequest, Narrative, RecordedRain, ScenarioRequest, ScenarioResult, simulate
from ..land_evidence import HistoryEvidence, InspectionEvidence, PlotEvidence
from ..land_narrative import ai_available, generate_narrative
from ..land_guidance import GuidanceRequest, LandGuidance, Purpose, Role, build_guidance
from ..providers.base import ProviderError
from ..providers.land_evidence import build_history, build_inspection, build_plot_evidence, load_rain
from ..providers.land_optical import LandStage, build_profile
from ..providers.terrain import TerrainGrid, build_terrain, sampling_grid
from ..reports.land_pdf import build_land_report

DEMO_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "land_demos"
DEMO_IDS = ("punjab-farmland", "thar-dryland")
logger = logging.getLogger(__name__)
Evidence = TypeVar("Evidence", bound=BaseModel)


def read_demos(directory: Path) -> dict[str, LandBundle]:
    demos = {}
    for identifier in DEMO_IDS:
        folder = directory / identifier
        if not folder.exists():
            continue
        try:
            profile = LandProfile.model_validate_json((folder / "profile.json").read_bytes())
            with Image.open(folder / "cover.png", formats=("PNG",)) as image:
                cover = np.array(image, dtype=np.uint8)
            if profile.id != identifier or cover.ndim != 2 or not profile.scenario_period:
                raise ValueError("Invalid demo manifest or scenario grid")
            demos[identifier] = LandBundle(profile, cover)
        except (OSError, ValueError) as error:
            logger.warning("Skipping incomplete land demo %s (%s)", identifier, type(error).__name__)
    return demos


def land_router(settings: Settings, demo_directory: Path = DEMO_DIRECTORY) -> APIRouter:
    router = APIRouter(prefix="/api/land")
    demos = read_demos(demo_directory)
    live: OrderedDict[str, LandBundle] = OrderedDict()
    lock = Lock()
    permits = BoundedSemaphore(2)
    ai_permit = BoundedSemaphore(1)
    guidance_cache: OrderedDict[tuple[str, Role, Purpose], Narrative] = OrderedDict()
    terrain_cache: OrderedDict[str, TerrainGrid] = OrderedDict()

    def lookup(identifier: str) -> LandBundle:
        if identifier in demos:
            return demos[identifier]
        with lock:
            if identifier in live:
                live.move_to_end(identifier)
                return live[identifier]
        raise HTTPException(status_code=404, detail="This land analysis has expired or does not exist.")

    @router.get("/catalog")
    def list_demos():
        return {"demos": [{"id": key, "title": bundle.profile.title, "terrain": bundle.profile.terrain}
                          for key, bundle in demos.items()],
                "ai_available": ai_available()}

    @router.get("/analyses/{identifier}", response_model=LandProfile)
    def get_analysis(identifier: str) -> LandProfile:
        return lookup(identifier).profile

    def run_analysis(request: LandRequest, progress: Callable[[LandStage], None] | None = None) -> LandProfile:
        if not settings.earth_engine_project:
            raise HTTPException(status_code=503, detail="Live land observations require Earth Engine. The two offline demos are available.")
        if not permits.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Two land analyses are running. Try again shortly.")
        try:
            bundle = build_profile(settings.earth_engine_project, request, settings.max_aoi_km2, progress)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        finally:
            permits.release()
        with lock:
            live[bundle.profile.id] = bundle
            if len(live) > 12:
                live.popitem(last=False)
        return bundle.profile

    @router.post("/analyses", response_model=LandProfile, status_code=201)
    def create_analysis(request: LandRequest) -> LandProfile:
        return run_analysis(request)

    @router.post("/analyses/stream", response_class=StreamingResponse)
    async def stream_analysis(request: LandRequest) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            loop = asyncio.get_running_loop()
            output: asyncio.Queue[tuple[str, str | LandProfile]] = asyncio.Queue()

            def emit(kind: str, data: str | LandProfile) -> None:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(output.put_nowait, (kind, data))

            def work() -> None:
                try:
                    emit("result", run_analysis(request, lambda stage: emit("stage", stage)))
                except HTTPException as error:
                    emit("error", str(error.detail))
                except Exception:
                    logger.exception("Streaming land analysis failed")
                    emit("error", "Land analysis could not finish. Try again with a shorter window or smaller boundary.")

            task = asyncio.create_task(asyncio.to_thread(work))
            try:
                while True:
                    kind, data = await output.get()
                    if kind == "result" and isinstance(data, LandProfile):
                        yield '{"type":"result","data":' + data.model_dump_json() + "}\n"
                    else:
                        yield json.dumps({"type": kind, "data": data}) + "\n"
                    if kind != "stage":
                        break
            finally:
                task.cancel()

        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    def evidence(identifier: str, name: str, schema: type[Evidence], fetch: Callable[[str], Evidence]) -> Evidence:
        if identifier in demos:
            try:
                return schema.model_validate_json((demo_directory / identifier / f"{name}.json").read_bytes())
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                logger.warning("Could not read archived %s evidence for %s", name, identifier)
        if not settings.earth_engine_project:
            raise HTTPException(status_code=503, detail="This evidence needs Earth Engine or a matching offline demo.")
        if not permits.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Satellite processing is busy. Try again shortly.")
        try:
            return fetch(settings.earth_engine_project)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        finally:
            permits.release()

    @router.get("/analyses/{identifier}/inspection", response_model=InspectionEvidence)
    def inspection(identifier: str) -> InspectionEvidence:
        profile = lookup(identifier).profile
        return evidence(identifier, "inspection", InspectionEvidence, lambda project: build_inspection(project, profile))

    @router.get("/analyses/{identifier}/history", response_model=HistoryEvidence)
    def history(identifier: str) -> HistoryEvidence:
        profile = lookup(identifier).profile
        return evidence(identifier, "history", HistoryEvidence, lambda project: build_history(project, profile))

    @router.get("/analyses/{identifier}/plot", response_model=PlotEvidence)
    def plot(identifier: str) -> PlotEvidence:
        profile = lookup(identifier).profile
        return evidence(identifier, "plot", PlotEvidence, lambda project: build_plot_evidence(project, profile.aoi))

    def run_scenario(bundle: LandBundle, inputs: ScenarioRequest, rain: RecordedRain | None = None) -> ScenarioResult:
        try:
            grid = sampling_grid(bundle.profile.aoi)
        except ValueError:
            grid = None
        try:
            return simulate(bundle, inputs, grid, rain)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/analyses/{identifier}/scenario", response_model=ScenarioResult)
    def scenario(identifier: str, inputs: ScenarioRequest) -> ScenarioResult:
        return run_scenario(lookup(identifier), inputs)

    @router.post("/analyses/{identifier}/monsoon/{year}", response_model=ScenarioResult)
    def monsoon(identifier: str, year: int, inputs: ScenarioRequest) -> ScenarioResult:
        bundle = lookup(identifier)
        if not 1981 <= year <= date.today().year or date(year, 7, 1) + timedelta(days=42) > date.today():
            raise HTTPException(status_code=422, detail="Choose a past July with at least six weeks of rainfall records.")
        start = date(year, 7, 1)
        rain = evidence(identifier, f"monsoon-{year}", RecordedRain,
                        lambda project: load_rain(project, bundle.profile.aoi, start, 42))
        if rain.start != start or len(rain.daily_mm) != 42:
            raise HTTPException(status_code=502, detail="The July rainfall record is incomplete.")
        return run_scenario(bundle, inputs, rain.model_copy(update={"daily_mm": rain.daily_mm[:inputs.days]}))

    @router.get("/analyses/{identifier}/terrain", response_model=TerrainGrid)
    def terrain(identifier: str) -> TerrainGrid:
        profile = lookup(identifier).profile
        with lock:
            saved = terrain_cache.get(identifier)
            if saved is not None:
                terrain_cache.move_to_end(identifier)
                return saved
        if identifier in demos:
            path = demo_directory / identifier / "terrain.json"
            try:
                grid = TerrainGrid.model_validate_json(path.read_bytes())
            except (OSError, ValueError) as error:
                raise HTTPException(status_code=404, detail="This archived case has no terrain grid.") from error
        else:
            if not settings.earth_engine_project:
                raise HTTPException(status_code=503, detail="Sampling a new terrain grid requires Earth Engine.")
            if not permits.acquire(blocking=False):
                raise HTTPException(status_code=429, detail="Satellite processing is busy. Try opening the terrain again shortly.")
            try:
                grid = build_terrain(settings.earth_engine_project, profile.aoi)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            except ProviderError as error:
                raise HTTPException(status_code=502, detail=str(error)) from error
            finally:
                permits.release()
        with lock:
            terrain_cache[identifier] = grid
            if len(terrain_cache) > 12:
                terrain_cache.popitem(last=False)
        return grid

    @router.post("/analyses/{identifier}/explain", response_model=Narrative)
    def explain(identifier: str) -> Narrative:
        bundle = lookup(identifier)
        if bundle.profile.narrative is not None:
            return bundle.profile.narrative
        if identifier in demos:
            raise HTTPException(status_code=409, detail="This offline bundle has no reviewed AI summary. The measured report is available.")
        if not ai_permit.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="An AI summary is being generated. Try again shortly.")
        try:
            narrative = generate_narrative(bundle.profile)
            with lock:
                if identifier in live:
                    live[identifier] = replace(bundle, profile=bundle.profile.model_copy(update={"narrative": narrative}))
            return narrative
        except ValueError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        finally:
            ai_permit.release()

    @router.post("/analyses/{identifier}/guidance", response_model=LandGuidance)
    def guidance(identifier: str, request: GuidanceRequest) -> LandGuidance:
        profile = lookup(identifier).profile
        response = build_guidance(profile, request)
        if not request.use_ai:
            return response
        if not ai_available():
            response.ai_status = "unavailable"
            return response
        key = (identifier, request.role, request.purpose)
        with lock:
            narrative = guidance_cache.get(key)
            if narrative is not None:
                guidance_cache.move_to_end(key)
        if narrative is not None:
            response.narrative, response.ai_status = narrative, "ready"
            return response
        if not ai_permit.acquire(blocking=False):
            response.ai_status = "busy"
            return response
        try:
            narrative = generate_narrative(profile, request)
            with lock:
                guidance_cache[key] = narrative
                if len(guidance_cache) > 32:
                    guidance_cache.popitem(last=False)
            response.narrative, response.ai_status = narrative, "ready"
        except (RuntimeError, ValueError):
            response.ai_status = "failed"
        finally:
            ai_permit.release()
        return response

    @router.get("/analyses/{identifier}/report.pdf")
    def report(identifier: str) -> Response:
        profile = lookup(identifier).profile
        return Response(build_land_report(profile), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="land-{profile.id}.pdf"', "Cache-Control": "no-store"})

    return router
