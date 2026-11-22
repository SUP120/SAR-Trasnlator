from datetime import UTC, date, datetime

import numpy as np
from scipy.ndimage import median_filter
from shapely.geometry import shape

from ..aoi import AoiPolygon
from ..pipeline.pairing import GeometryKey, Pair, Scene
from ..pipeline.raster import PROJECT, Grid, Parameters, RasterStack
from ..pipeline.windows import EventDate

EXAMPLE_SLUG = "synthetic-river-valley"
EXAMPLE_TITLE = "Synthetic river valley"
EXAMPLE_AOI = AoiPolygon(type="Polygon", coordinates=[[
    (91.735, 26.151), (91.768, 26.151), (91.768, 26.174), (91.735, 26.174), (91.735, 26.151),
]])
EXAMPLE_WINDOW = EventDate(kind="event", date=date(2020, 6, 25))
DAYS = (date(2020, 6, 10), date(2020, 6, 16), date(2020, 6, 22), date(2020, 6, 28), date(2020, 7, 4))


class SyntheticProvider:
    def latest(self, area: AoiPolygon) -> date:
        return DAYS[-1]

    def scenes(self, area: AoiPolygon, start: date, end: date) -> list[Scene]:
        footprint = shape(area.model_dump())
        geometry = GeometryKey("ASCENDING", 113, "IW", ("VH", "VV"))
        return [Scene(f"synthetic-{day}", datetime.combine(day, datetime.min.time(), UTC), "Synthetic A", geometry, footprint)
                for day in DAYS if start <= day < end]

    def pixels(self, area: AoiPolygon, pair: Pair, grid: Grid, params: Parameters) -> RasterStack:
        # Draw an invented VV pattern in a fixed grid to exercise the same detection and rendering code.
        y, x = np.meshgrid(np.linspace(0, 1, grid.height), np.linspace(0, 1, grid.width), indexing="ij")
        river_center = 0.56 + 0.16 * np.sin(6.5 * x + 0.4) - 0.1 * x
        bank_distance = y - river_center
        river = np.abs(bank_distance) < 0.027 + 0.007 * np.sin(x * 23)
        floodplain = (np.abs((x - 0.55) / 0.34) ** 2 + ((bank_distance - 0.06) / 0.14) ** 2 < 1)
        floodplain |= ((x - 0.26) / .18) ** 2 + ((bank_distance + .05) / .105) ** 2 < 1
        slope = np.where(y < 0.17 + 0.06 * np.sin(9 * x), 8, 2).astype(np.float32)
        hand = np.where(y > 0.83, 18, 5).astype(np.float32)
        noise = np.random.default_rng(23).normal(0, 1.1, x.shape)
        terrain = -11 + 2.3 * np.sin(12 * x + 7 * y) + 1.4 * np.cos(42 * x - 22 * y) + noise
        before = np.where(river, -22 + noise, terrain)
        after = np.where(floodplain | river, -23 + noise, terrain + 0.6 * np.sin(46 * y))
        radius = params.speckle_radius_m / grid.scale_m
        axis = np.arange(-int(radius), int(radius) + 1)
        kernel = axis[:, None] ** 2 + axis ** 2 <= radius ** 2
        before = median_filter(before, footprint=kernel)
        after = median_filter(after, footprint=kernel)
        before[(x > 0.89) & (y < 0.24)] = np.nan
        # The fixed example bbox is snapped to an equal-area grid. Select sample centres inside the original rectangle.
        west, south = PROJECT.transform(*area.coordinates[0][0])
        east, north = PROJECT.transform(*area.coordinates[0][2])
        center_x = grid.west + (np.arange(grid.width) + .5) * grid.scale_m
        center_y = grid.north - (np.arange(grid.height) + .5) * grid.scale_m
        aoi = ((center_x >= west) & (center_x <= east))[None, :] & ((center_y >= south) & (center_y <= north))[:, None]
        return RasterStack(grid, before, after, aoi,
                           np.full(x.shape, grid.scale_m ** 2, dtype=np.float64),
                           np.where(river, 99, 0), slope, hand)
