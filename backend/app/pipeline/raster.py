from dataclasses import dataclass
from io import BytesIO
from math import ceil, floor
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from pyproj import CRS as CoordinateReferenceSystem
from pyproj import Transformer
from shapely import transform
from scipy import ndimage
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..aoi import AoiPolygon
from .pairing import Scenes

CRS = "EPSG:6933"
# Earth Engine accepts this equal-area CRS as WKT1, but cannot resolve its EPSG code.
EARTH_ENGINE_CRS_WKT = CoordinateReferenceSystem.from_user_input(CRS).to_wkt(version="WKT1_GDAL")
MAX_GRID_CELLS = 1_500_000
PROJECT = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
TO_WEB = Transformer.from_crs(CRS, "EPSG:3857", always_xy=True)
FROM_WEB = Transformer.from_crs("EPSG:3857", CRS, always_xy=True)
WEB_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
LayerName = Literal["before", "after", "change"]
LAYER_NAMES: tuple[LayerName, ...] = ("before", "after", "change")


class GridError(ValueError):
    pass


def project(geometry: BaseGeometry) -> BaseGeometry:
    return transform(geometry, PROJECT.transform, interleaved=False)


@dataclass(frozen=True)
class Grid:
    west: float
    north: float
    width: int
    height: int
    scale_m: int

    @classmethod
    def around(cls, area: AoiPolygon, scale: int) -> "Grid":
        polygon = shape(area.model_dump())
        if polygon.bounds[1] < -86 or polygon.bounds[3] > 86:
            raise GridError("The processing grid covers latitudes between 86°S and 86°N.")
        west, south, east, north = project(polygon).bounds
        x, y = floor(west / scale) * scale, ceil(north / scale) * scale
        width, height = ceil((east - x) / scale), ceil((y - south) / scale)
        if width * height > MAX_GRID_CELLS or max(width, height) > 4096:
            raise GridError("The processing grid is too wide or tall. Draw a more compact study area.")
        return cls(x, y, width, height, scale)

    def ee_grid(self) -> dict:
        return {
            "dimensions": {"width": self.width, "height": self.height},
            "crsWkt": EARTH_ENGINE_CRS_WKT,
            "affineTransform": {
                "scaleX": self.scale_m, "scaleY": -self.scale_m,
                "translateX": self.west, "translateY": self.north,
            },
        }


def footprint_coverage(area: BaseGeometry, pre: Scenes, post: Scenes) -> float:
    projected = project(area)
    before = unary_union([project(scene.footprint) for scene in pre])
    after = unary_union([project(scene.footprint) for scene in post])
    return min(1.0, projected.intersection(before).intersection(after).area / projected.area)


@dataclass(frozen=True)
class Parameters:
    scale_m: int = 10
    water_db: float = -15
    change_db: float = -3
    speckle_radius_m: int = 40
    permanent_water_pct: int = 90
    max_slope_deg: int = 5
    max_hand_m: int = 15
    min_cluster_pixels: int = 8


@dataclass(frozen=True)
class RasterStack:
    grid: Grid
    pre_vv: NDArray
    post_vv: NDArray
    aoi: NDArray[np.bool_]
    pixel_area: NDArray
    occurrence: NDArray
    slope: NDArray
    hand: NDArray | None


@dataclass(frozen=True)
class Detection:
    flood: NDArray[np.bool_]
    stats: dict[str, float]
    excluded_ha: dict[str, float]
    warnings: tuple[str, ...]


def detect(stack: RasterStack, settings: Parameters) -> Detection:
    pre, post = stack.pre_vv, stack.post_vv
    valid = stack.aoi & np.isfinite(pre) & np.isfinite(post)
    existing = valid & ((pre < settings.water_db) | (stack.occurrence >= settings.permanent_water_pct))
    terrain = ~np.isfinite(stack.slope) | (stack.slope > settings.max_slope_deg)
    warnings: list[str] = []
    if stack.hand is not None:
        terrain |= (stack.hand > settings.max_hand_m)
        if np.any(valid & ~np.isfinite(stack.hand)):
            warnings.append("Height-above-drainage data is unavailable for part of the observation area.")
    else:
        warnings.append("The height-above-drainage mask was unavailable.")
    if np.any(valid & ~np.isfinite(stack.slope)):
        warnings.append("Pixels with no slope data were excluded from detection.")

    candidate = valid & (post < settings.water_db) & ((post - pre) < settings.change_db)
    removed_water = candidate & existing
    removed_terrain = candidate & ~existing & terrain
    filtered = candidate & ~existing & ~terrain
    components, _ = ndimage.label(filtered, structure=np.ones((3, 3), dtype=np.uint8))
    sizes = np.bincount(components.ravel())
    sizes[0] = 0
    flood = sizes[components] >= settings.min_cluster_pixels

    def area(mask: NDArray[np.bool_]) -> float:
        return float(stack.pixel_area[mask].sum(dtype=np.float64))

    aoi_m2 = area(stack.aoi)
    if aoi_m2 <= 0:
        raise GridError("The study boundary contains no whole grid samples at the configured scale.")
    flood_m2 = area(flood)
    return Detection(flood, {
        "sampled_aoi_km2": aoi_m2 / 1_000_000,
        "flood_ha": flood_m2 / 10_000,
        "flood_km2": flood_m2 / 1_000_000,
        "flood_pct_of_aoi": 100 * flood_m2 / aoi_m2,
        "preexisting_water_ha": area(existing) / 10_000,
        "valid_coverage_pct": 100 * area(valid) / aoi_m2,
        "masked_terrain_pct": 100 * area(stack.aoi & terrain) / aoi_m2,
    }, {
        "preexisting_water": area(removed_water) / 10_000,
        "terrain": area(removed_terrain) / 10_000,
        "small_clusters": area(filtered & ~flood) / 10_000,
    }, tuple(warnings))


@dataclass(frozen=True)
class RenderedLayers:
    bounds: tuple[tuple[float, float], tuple[float, float]]
    pngs: dict[LayerName, bytes]


def render_layers(stack: RasterStack, flood: NDArray[np.bool_]) -> RenderedLayers:
    grid = stack.grid
    west, south, east, north = TO_WEB.transform_bounds(
        grid.west, grid.north - grid.height * grid.scale_m,
        grid.west + grid.width * grid.scale_m, grid.north,
    )
    pixel_size = max((east - west) / 600, (north - south) / 600)
    width, height = max(1, ceil((east - west) / pixel_size)), max(1, ceil((north - south) / pixel_size))
    x = west + (np.arange(width) + 0.5) * (east - west) / width
    y = north - (np.arange(height) + 0.5) * (north - south) / height
    xs, ys = FROM_WEB.transform(*np.meshgrid(x, y))
    columns = np.clip(((xs - grid.west) / grid.scale_m).astype(int), 0, grid.width - 1)
    rows = np.clip(((grid.north - ys) / grid.scale_m).astype(int), 0, grid.height - 1)
    inside = stack.aoi[rows, columns]

    def image(values: NDArray) -> NDArray[np.uint8]:
        view = values[rows, columns]
        shade = np.clip((np.nan_to_num(view, nan=-30) + 30) * 8, 16, 237).astype(np.uint8)
        alpha = np.where(inside & np.isfinite(view), 255, 0).astype(np.uint8)
        return np.stack((shade, shade, shade, alpha), axis=-1)

    def to_png(pixels: NDArray[np.uint8]) -> bytes:
        output = BytesIO()
        Image.fromarray(pixels).save(output, format="PNG")
        return output.getvalue()

    before, after = image(stack.pre_vv), image(stack.post_vv)
    change = after.copy()
    change[flood[rows, columns]] = (77, 224, 213, 255)
    sw_lon, sw_lat = WEB_TO_WGS84.transform(west, south)
    ne_lon, ne_lat = WEB_TO_WGS84.transform(east, north)
    return RenderedLayers(((sw_lat, sw_lon), (ne_lat, ne_lon)), {
        "before": to_png(before), "after": to_png(after), "change": to_png(change),
    })
