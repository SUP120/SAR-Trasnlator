from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl
from shapely.geometry import shape

from .aoi import AoiPolygon, validate_aoi
from .pipeline.pairing import GeometryKey, Rejection, Scene, select_pair
from .pipeline.quality import Quality, rate_quality
from .pipeline.raster import LAYER_NAMES, Grid, LayerName, Parameters, RenderedLayers, detect, footprint_coverage, render_layers
from .pipeline.windows import Periods, Preset, Window, resolve_window
from .providers.base import SarProvider
from .providers.synthetic import EXAMPLE_AOI, EXAMPLE_TITLE, EXAMPLE_WINDOW

Source = Literal["synthetic", "earth_engine"]
Stages = Literal["finding_scenes", "computing", "rendering"]
Classification = Literal["possible_flooding", "no_change_detected", "insufficient_data"]
METHOD_VERSION = "sar-vv-1"


class SyntheticRequest(BaseModel):
    source: Literal["synthetic"]


class LiveRequest(BaseModel):
    source: Literal["earth_engine"]
    aoi: AoiPolygon
    window: Window


AnalysisRequest = Annotated[SyntheticRequest | LiveRequest, Field(discriminator="source")]


class Observation(BaseModel):
    id: str
    acquired_at: datetime
    platform: str

    @classmethod
    def from_scene(cls, scene: Scene) -> "Observation":
        return cls(id=scene.id, acquired_at=scene.acquired_at, platform=scene.platform)


class Statistics(BaseModel):
    sampled_aoi_km2: float
    flood_ha: float
    flood_km2: float
    flood_pct_of_aoi: float
    preexisting_water_ha: float
    valid_coverage_pct: float
    masked_terrain_pct: float


class CachedEventProvenance(BaseModel):
    slug: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    reference_url: HttpUrl


class AnalysisResult(BaseModel):
    id: str
    source: Source
    title: str
    aoi: AoiPolygon
    aoi_area_km2: float
    periods: Periods
    geometry: GeometryKey
    pre: list[Observation]
    post: list[Observation]
    footprint_coverage_pct: float
    stats: Statistics
    masks_excluded_ha: dict[str, float]
    parameters: Parameters
    classification: Classification
    quality: Quality
    warnings: list[str]
    attributions: list[str]
    layers: dict[LayerName, str]
    bounds: tuple[tuple[float, float], tuple[float, float]]
    created_at: datetime
    method_version: str = METHOD_VERSION
    cached_event: CachedEventProvenance | None = None


@dataclass(frozen=True)
class Outcome:
    result: AnalysisResult | None
    rejections: tuple[Rejection, ...] = ()
    layers: RenderedLayers | None = None


def analysis_layer_paths(job_id: str) -> dict[LayerName, str]:
    return {name: f"analyses/{job_id}/layers/{name}.png" for name in LAYER_NAMES}


def run_analysis(
    job_id: str, request: AnalysisRequest, provider: SarProvider, params: Parameters, limit: float,
    progress: Callable[[Stages], None],
) -> Outcome:
    practice = isinstance(request, SyntheticRequest)
    aoi = EXAMPLE_AOI if practice else request.aoi
    window = EXAMPLE_WINDOW if practice else request.window
    aoi_area = validate_aoi(aoi, 100.0 if practice else limit).area_km2
    grid = Grid.around(aoi, params.scale_m)
    footprint = shape(aoi.model_dump())

    progress("finding_scenes")
    latest = provider.latest(aoi) if isinstance(window, Preset) else None
    if isinstance(window, Preset) and latest is None:
        return Outcome(None)
    periods = resolve_window(window, latest)
    before = provider.scenes(aoi, periods.start, periods.event)
    after = provider.scenes(aoi, periods.event, periods.end_exclusive)
    selection = select_pair(before, after, lambda pre, post: footprint_coverage(footprint, pre, post))
    pair = selection.pair
    if pair is None:
        return Outcome(None, selection.rejections)

    progress("computing")
    stack = provider.pixels(aoi, pair, grid, params)
    detection = detect(stack, params)
    stats = Statistics(**detection.stats)
    quality = rate_quality(pair, periods.event, stats.valid_coverage_pct, stats.masked_terrain_pct)
    classification: Classification = ("insufficient_data" if stats.valid_coverage_pct == 0 else
                                      "possible_flooding" if stats.flood_ha > 0 else "no_change_detected")
    warnings = list(detection.warnings)
    if stats.valid_coverage_pct < 95:
        warnings.append("Less than 95% of the study area had valid data in both composites.")
    warnings.extend([
        "Radar shadow and smooth surfaces can resemble water. Flooded vegetation and built-up areas may be missed.",
        "The observation dates may miss the flood peak. Composite medians can hide short-lived changes.",
    ])
    if practice:
        warnings.insert(0, "Synthetic example. The inputs are invented for practice and provide no evidence of an actual flood.")

    progress("rendering")
    layers = render_layers(stack, detection.flood)
    years = ", ".join(str(year) for year in sorted({scene.acquired_at.year for scene in (*pair.pre, *pair.post)}))
    sources = (["Synthetic radar and terrain inputs generated by SAR Translator."] if practice else [
        f"Contains modified Copernicus Sentinel data {years}.",
        "EC JRC/Google Global Surface Water v1.4; MERIT Hydro (Yamazaki et al. 2019).",
        "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
    ])
    result = AnalysisResult(
        id=job_id, source=request.source, title=EXAMPLE_TITLE if practice else "Sentinel-1 observation comparison",
        aoi=aoi, aoi_area_km2=aoi_area, periods=periods, geometry=pair.pre[0].geometry,
        pre=[Observation.from_scene(scene) for scene in pair.pre], post=[Observation.from_scene(scene) for scene in pair.post],
        footprint_coverage_pct=100 * pair.coverage, stats=stats, masks_excluded_ha=detection.excluded_ha,
        parameters=params, classification=classification, quality=quality, warnings=warnings, attributions=sources,
        layers=analysis_layer_paths(job_id),
        bounds=layers.bounds, created_at=datetime.now(UTC),
    )
    return Outcome(result, selection.rejections, layers)
