from math import ceil

import numpy as np
from pydantic import BaseModel, FiniteFloat, Field, model_validator
from shapely.geometry import shape

from ..aoi import AoiPolygon
from ..pipeline.raster import Grid, project
from .base import ProviderError
from .earth_engine import DEM, MISSING, EarthEngineProvider

MAX_SIDE = 56
SOURCE_CREDIT = (
    "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH "
    "2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved."
)


class TerrainGrid(BaseModel):
    cell_m: int = Field(ge=30)
    elevations_m: list[list[FiniteFloat | None]] = Field(min_length=2, max_length=MAX_SIDE)
    source: str = DEM
    credit: str = SOURCE_CREDIT

    @model_validator(mode="after")
    def regular_grid(self) -> "TerrainGrid":
        width = len(self.elevations_m[0])
        if not 2 <= width <= MAX_SIDE or any(len(row) != width for row in self.elevations_m):
            raise ValueError("The elevation grid must be rectangular.")
        return self


def sampling_grid(aoi: AoiPolygon) -> Grid:
    west, south, east, north = project(shape(aoi.model_dump())).bounds
    # Leave room for the equal-area grid snapping outward by up to one cell.
    scale = max(30, ceil(max(east - west, north - south) / (MAX_SIDE - 2)))
    grid = Grid.around(aoi, scale)
    if min(grid.height, grid.width) < 2:
        raise ValueError("A wider study boundary is needed for the 3D elevation view.")
    return grid


def build_terrain(project_id: str, aoi: AoiPolygon) -> TerrainGrid:
    grid = sampling_grid(aoi)
    provider = EarthEngineProvider(project_id)
    ee = provider._sdk()
    area = provider._area(aoi)
    image = ee.ImageCollection(DEM).filterBounds(area).select("DEM").mosaic().clip(area).toFloat().unmask(MISSING, False)
    try:
        pixels = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": grid.ee_grid()})["DEM"]
    except ee.EEException as error:
        raise ProviderError("Earth Engine could not sample the elevation surface.") from error
    valid = np.isfinite(pixels) & (pixels != MISSING)
    if not np.any(valid[:-1, :-1] & valid[1:, 1:] & (valid[:-1, 1:] | valid[1:, :-1])):
        raise ValueError("Too few adjacent elevation samples were available for the 3D surface.")
    return TerrainGrid(cell_m=grid.scale_m, elevations_m=[
        [round(float(value), 1) if available else None for value, available in zip(row, mask, strict=True)]
        for row, mask in zip(pixels, valid, strict=True)
    ])
