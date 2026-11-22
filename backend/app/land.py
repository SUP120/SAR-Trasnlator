from base64 import b64encode
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from .aoi import AoiPolygon
from .pipeline.raster import Grid

CLASSES = ("Water", "Trees", "Grass", "Flooded vegetation", "Crops", "Shrub and scrub", "Built area", "Bare ground", "Snow and ice")
MISSING_CLASS = 255
GRID_M = 30
MIN_CLEAR = 0.2
# These class factors are scenario assumptions. They are not local calibrations.
INFILTRATION_BY_CLASS = (0, .80, .75, 0, .70, .65, .15, .45, 0)
MODELED_CLASSES = tuple(index for index, factor in enumerate(INFILTRATION_BY_CLASS) if factor)


class LandRequest(BaseModel):
    aoi: AoiPolygon
    end: date
    months: Literal[3, 6, 12] = 6

    @model_validator(mode="after")
    def available_dates(self) -> "LandRequest":
        if not date(2018, 1, 1) <= self.end <= date.today():
            raise ValueError("Choose a date between January 2018 and today.")
        return self


class SceneDate(BaseModel):
    id: str
    acquired_at: datetime


class ImageOffset(BaseModel):
    east_m: int
    north_m: int
    matched_blocks: int
    from_period: date


class LandObservation(BaseModel):
    start: date
    end: date
    scenes: list[SceneDate]
    clear_pct: float
    ndvi: float | None
    ndmi: float | None
    mapped_water_pct: float | None
    soil_moisture_pct: float | None
    land_cover_pct: dict[str, float]
    classified_pct: float
    image_offset: ImageOffset | None = None
    image: str | None


class Narrative(BaseModel):
    source: Literal["template", "ai", "cached_ai"]
    text: str


class LandProfile(BaseModel):
    id: str
    title: str
    terrain: Literal["farmland", "dryland"] | None = None
    aoi: AoiPolygon
    area_km2: float
    grid_m: int = GRID_M
    observations: list[LandObservation]
    scenario_period: date | None
    narrative: Narrative | None = None


@dataclass(frozen=True)
class LandBundle:
    profile: LandProfile
    cover: NDArray[np.uint8] | None


class ScenarioRequest(BaseModel):
    days: Literal[14, 28, 42] = 28
    rain_mm_week: float = Field(ge=0, le=300, allow_inf_nan=False)
    demand_mm_day: float = Field(ge=0, le=15, allow_inf_nan=False)
    storage_capacity_mm: float = Field(ge=20, le=300, allow_inf_nan=False)
    initial_storage_pct: float = Field(ge=0, le=100, allow_inf_nan=False)


class ScenarioFrame(BaseModel):
    day: int
    mean_storage_pct: float
    low_storage_area_pct: float
    mean_overflow_mm: float
    image: str
    terrain_storage_pct: list[list[float | None]] | None = None


class RecordedRain(BaseModel):
    start: date
    daily_mm: list[Annotated[float, Field(ge=0, allow_inf_nan=False)]] = Field(min_length=14, max_length=42)
    source: str


class ScenarioResult(BaseModel):
    frames: list[ScenarioFrame]
    modeled_cells: int
    baseline: date
    inputs: ScenarioRequest
    recorded_rain: RecordedRain | None = None


def png_url(rgba: NDArray[np.uint8]) -> str:
    image = Image.fromarray(rgba)
    image.thumbnail((256, 256), Image.Resampling.NEAREST)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + b64encode(buffer.getvalue()).decode("ascii")


def image_offset(before: NDArray, after: NDArray, baseline: date) -> ImageOffset | None:
    """Estimate apparent translation over textured optical blocks at grid resolution."""
    size, reach = 12, 2
    height, width = before.shape
    stride = size * max(1, (max(height, width) + 143) // 144)
    shifts: list[tuple[int, int]] = []
    for row in range(reach, height - size - reach + 1, stride):
        for col in range(reach, width - size - reach + 1, stride):
            reference = before[row:row + size, col:col + size]
            scores: list[tuple[float, int, int]] = []
            if np.isfinite(reference).sum() < size * size * 0.8:
                continue
            for dy in range(-reach, reach + 1):
                for dx in range(-reach, reach + 1):
                    target = after[row + dy:row + dy + size, col + dx:col + dx + size]
                    valid = np.isfinite(reference) & np.isfinite(target)
                    if valid.sum() < size * size * 0.8:
                        continue
                    first, second = reference[valid], target[valid]
                    if min(first.std(), second.std()) < 75:
                        continue
                    score = float(np.corrcoef(first, second)[0, 1])
                    scores.append((score, dx, dy))
            scores.sort(reverse=True)
            if len(scores) >= 2 and scores[0][0] >= 0.8 and scores[0][0] - scores[1][0] >= 0.05:
                shifts.append(scores[0][1:])
    if len(shifts) < 3:
        return None
    offsets, counts = np.unique(np.asarray(shifts), axis=0, return_counts=True)
    mode = int(np.argmax(counts))
    dx, dy = offsets[mode]
    if counts[mode] / len(shifts) < 0.6 or max(abs(dx), abs(dy)) == reach:
        return None
    return ImageOffset(east_m=int(dx * GRID_M), north_m=int(-dy * GRID_M),
                       matched_blocks=int(counts[mode]), from_period=baseline)


def simulate(bundle: LandBundle, inputs: ScenarioRequest, terrain_grid: Grid | None = None,
             recorded_rain: RecordedRain | None = None) -> ScenarioResult:
    cover, baseline = bundle.cover, bundle.profile.scenario_period
    if cover is None or baseline is None:
        raise ValueError("A classified observation is required for the scenario.")
    modeled = np.isin(cover, MODELED_CLASSES)
    if not modeled.any():
        raise ValueError("The classified area has no eligible land pixels.")
    daily_rain = recorded_rain.daily_mm if recorded_rain else [inputs.rain_mm_week / 7] * inputs.days
    if len(daily_rain) != inputs.days:
        raise ValueError("The rainfall record must cover every day of the replay.")
    infiltration = np.asarray(INFILTRATION_BY_CLASS)[cover[modeled]]
    capacity = inputs.storage_capacity_mm
    storage = np.full(infiltration.shape, capacity * inputs.initial_storage_pct / 100)
    overflow = np.zeros_like(storage)
    if terrain_grid is not None:
        source_grid = Grid.around(bundle.profile.aoi, GRID_M)
        if cover.shape != (source_grid.height, source_grid.width):
            terrain_grid = None
    if terrain_grid is not None:
        # Both grids use EPSG:6933. Find the modeled cell containing each terrain vertex.
        x = terrain_grid.west + (np.arange(terrain_grid.width) + .5) * terrain_grid.scale_m
        y = terrain_grid.north - (np.arange(terrain_grid.height) + .5) * terrain_grid.scale_m
        cols = np.floor((x - source_grid.west) / source_grid.scale_m).astype(int)
        rows = np.floor((source_grid.north - y) / source_grid.scale_m).astype(int)
        inside = ((rows >= 0) & (rows < source_grid.height))[:, None] & ((cols >= 0) & (cols < source_grid.width))[None, :]
        rows = np.clip(rows, 0, source_grid.height - 1)
        cols = np.clip(cols, 0, source_grid.width - 1)
        included = inside & modeled[np.ix_(rows, cols)]
    frames = []
    for day in range(inputs.days + 1):
        if day:
            available = storage + daily_rain[day - 1] * infiltration
            overflow += np.maximum(available - capacity, 0)
            storage = np.maximum(np.minimum(available, capacity) - inputs.demand_mm_day, 0)
        if day % 7:
            continue
        fraction = storage / capacity
        rgba = np.zeros((*cover.shape, 4), dtype=np.uint8)
        dry, wet = np.array([237, 152, 72]), np.array([48, 164, 207])
        rgba[modeled, :3] = (dry + (wet - dry) * fraction[:, None]).astype(np.uint8)
        rgba[modeled, 3] = 255
        terrain_storage = None
        if terrain_grid is not None:
            percentages = np.zeros(cover.shape)
            percentages[modeled] = np.round(100 * fraction, 1)
            sampled = percentages[np.ix_(rows, cols)]
            terrain_storage = [[float(value) if valid else None for value, valid in zip(row, mask, strict=True)]
                               for row, mask in zip(sampled, included, strict=True)]
        frames.append(ScenarioFrame(day=day, mean_storage_pct=round(float(fraction.mean()) * 100, 1),
                                    low_storage_area_pct=round(float((fraction < 0.25).mean()) * 100, 1),
                                    mean_overflow_mm=round(float(overflow.mean()), 1), image=png_url(rgba),
                                    terrain_storage_pct=terrain_storage))
    return ScenarioResult(frames=frames, modeled_cells=int(modeled.sum()), baseline=baseline, inputs=inputs,
                          recorded_rain=recorded_rain)
