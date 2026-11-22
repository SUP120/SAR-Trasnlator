from datetime import date

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from scipy import ndimage

from .land import SceneDate
from .pipeline.raster import Grid, PROJECT


class ImageEvidence(BaseModel):
    start: date
    end: date
    clear_pct: float
    image: str
    scenes: list[SceneDate]


class HistoryEvidence(BaseModel):
    earlier: ImageEvidence
    recent: ImageEvidence
    grid_m: int


class FieldPatch(BaseModel):
    id: int
    hectares: float
    earlier_greenness: float
    recent_greenness: float
    x_pct: float
    y_pct: float
    latitude: float
    longitude: float


class InspectionEvidence(BaseModel):
    earlier: list[ImageEvidence]
    recent: ImageEvidence
    shared_pct: float
    grid_m: int
    min_drop: float
    min_cells: int
    highlight: str
    patches: list[FieldPatch]


class PlotEvidence(BaseModel):
    water_area_pct: float | None
    water_coverage_pct: float
    average_slope_deg: float | None
    slope_coverage_pct: float


MIN_GREENNESS_DROP = 0.15
MIN_PATCH_CELLS = 4


def find_patches(grid: Grid, inside: NDArray[np.bool_], latest: NDArray, reference: NDArray,
                 crops: NDArray[np.bool_]) -> tuple[float, NDArray[np.bool_], list[FieldPatch]]:
    shared = inside & np.isfinite(latest) & np.isfinite(reference)
    coverage = float(shared.sum()) / max(1, int(inside.sum()))
    # Limit flags to land classified as crops in either comparable period.
    candidate = shared & crops & (reference - latest >= MIN_GREENNESS_DROP) & (reference >= 0.25)
    labels, count = ndimage.label(candidate, np.ones((3, 3), dtype=bool))
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    ranked = sorted((index for index in range(1, count + 1) if sizes[index] >= MIN_PATCH_CELLS),
                    key=lambda index: (-sizes[index], index))[:8] if coverage >= 0.2 else []
    patches = []
    for index, label in enumerate(ranked, 1):
        mask = labels == label
        rows, cols = np.nonzero(mask)
        nearest = np.argmin((rows - rows.mean()) ** 2 + (cols - cols.mean()) ** 2)
        row, col = rows[nearest] + 0.5, cols[nearest] + 0.5
        lon, lat = PROJECT.transform(grid.west + col * grid.scale_m, grid.north - row * grid.scale_m, direction="INVERSE")
        patches.append(FieldPatch(
            id=index, hectares=round(int(sizes[label]) * grid.scale_m ** 2 / 10_000, 2),
            earlier_greenness=round(float(reference[mask].mean()), 3), recent_greenness=round(float(latest[mask].mean()), 3),
            x_pct=round(float(col / grid.width * 100), 3), y_pct=round(float(row / grid.height * 100), 3),
            latitude=round(lat, 6), longitude=round(lon, 6),
        ))
    return round(100 * coverage, 2), np.isin(labels, ranked), patches
