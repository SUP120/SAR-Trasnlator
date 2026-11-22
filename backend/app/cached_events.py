import logging
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, HttpUrl

from .analysis import AnalysisResult, CachedEventProvenance, analysis_layer_paths
from .jobs import Snapshot
from .pipeline.pairing import Rejection
from .pipeline.raster import LAYER_NAMES, RenderedLayers

EVENTS_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "demo_events"
logger = logging.getLogger(__name__)


class EventManifest(BaseModel):
    schema_version: Literal[1]
    reference_url: HttpUrl
    result: dict[str, Any]
    rejections: tuple[Rejection, ...] = ()


@dataclass(frozen=True)
class CachedEvent:
    slug: str
    title: str
    snapshot: Snapshot
    layers: RenderedLayers


def load_event(directory: Path) -> CachedEvent:
    manifest_bytes = (directory / "event.json").read_bytes()
    manifest = EventManifest.model_validate_json(manifest_bytes)
    provenance = CachedEventProvenance(slug=directory.name, reference_url=manifest.reference_url)
    fingerprint = sha256(provenance.slug.encode() + b"\0" + manifest_bytes)
    images = {}
    dimensions = set()
    for name in LAYER_NAMES:
        png = (directory / f"{name}.png").read_bytes()
        with Image.open(BytesIO(png), formats=("PNG",)) as image:
            if image.mode != "RGBA":
                raise ValueError("Cached map layers must be RGBA PNGs.")
            dimensions.add(image.size)
            image.verify()
        images[name] = png
        fingerprint.update(png)
    if len(dimensions) != 1:
        raise ValueError("Cached map layers must share one grid.")

    result_id = fingerprint.hexdigest()[:32]
    result = AnalysisResult.model_validate({**manifest.result, "id": result_id,
                                            "layers": analysis_layer_paths(result_id), "cached_event": provenance})
    if result.source != "earth_engine" or not result.pre or not result.post:
        raise ValueError("Historical events require real before and after observations.")
    snapshot = Snapshot(id=result_id, source=result.source, status="done", result=result, rejections=manifest.rejections)
    return CachedEvent(provenance.slug, result.title, snapshot, RenderedLayers(result.bounds, images))


class EventCatalog:
    def __init__(self, root: Path = EVENTS_DIRECTORY):
        self.by_slug: dict[str, CachedEvent] = {}
        self.by_id: dict[str, CachedEvent] = {}
        for directory in sorted(root.iterdir()) if root.is_dir() else ():
            if not directory.is_dir():
                continue
            try:
                event = load_event(directory)
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
                logger.warning("Skipping historical event %s (%s)", directory.name, type(error).__name__)
                continue
            self.by_slug[event.slug] = event
            self.by_id[event.snapshot.id] = event
