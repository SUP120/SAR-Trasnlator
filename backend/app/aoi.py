from typing import Annotated, Literal

from pydantic import BaseModel, Field, FiniteFloat
from pyproj import Geod
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

MAX_VERTICES = 500
WGS84 = Geod(ellps="WGS84")

Longitude = Annotated[FiniteFloat, Field(strict=True, ge=-180, le=180)]
Latitude = Annotated[FiniteFloat, Field(strict=True, ge=-90, le=90)]
Position = tuple[Longitude, Latitude]
Ring = Annotated[list[Position], Field(min_length=4, max_length=MAX_VERTICES + 1)]


class AoiPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: Annotated[list[Ring], Field(min_length=1, max_length=MAX_VERTICES // 3)]


class ValidatedAoi(BaseModel):
    area_km2: float
    max_area_km2: float


class InvalidAoi(ValueError):
    pass


def validate_aoi(geometry: AoiPolygon, max_area_km2: float) -> ValidatedAoi:
    rings = geometry.coordinates
    if sum(len(ring) - 1 for ring in rings) > MAX_VERTICES:
        raise InvalidAoi(f"Use at most {MAX_VERTICES} vertices across all rings.")
    if any(ring[0] != ring[-1] for ring in rings):
        raise InvalidAoi("Close all polygon rings and try again.")

    polygon = Polygon(rings[0], rings[1:])
    west, _, east, _ = polygon.bounds
    if east - west >= 180:
        raise InvalidAoi("Choose a smaller area on one side of the antimeridian.")
    if not polygon.is_valid:
        raise InvalidAoi("Draw a valid polygon with no crossing edges or overlapping rings.")

    square_metres, _ = WGS84.geometry_area_perimeter(orient(polygon, sign=1))
    area_km2 = abs(square_metres) / 1_000_000
    if area_km2 == 0:
        raise InvalidAoi("Draw a polygon that encloses a non-zero area.")
    if area_km2 > max_area_km2:
        raise InvalidAoi(f"This area is {area_km2:,.2f} km². Redraw it within the {max_area_km2:g} km² limit.")
    return ValidatedAoi(area_km2=area_km2, max_area_km2=max_area_km2)
