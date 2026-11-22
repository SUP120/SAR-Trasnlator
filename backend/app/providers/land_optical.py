from calendar import monthrange
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import numpy as np

from ..aoi import validate_aoi
from ..land import (CLASSES, GRID_M, MIN_CLEAR, MISSING_CLASS, MODELED_CLASSES, LandBundle, LandObservation,
                    LandProfile, LandRequest, SceneDate, image_offset, png_url)
from ..pipeline.raster import Grid
from .base import ProviderError
from .earth_engine import EarthEngineProvider

OPTICAL = "COPERNICUS/S2_SR_HARMONIZED"
COVER = "GOOGLE/DYNAMICWORLD/V1"
SOIL = "NASA/SMAP/SPL4SMGP/008"
BANDS = ("r", "g", "b", "red", "ndvi", "ndmi", "water", "cover", "aoi")
COVER_BANDS = ("water", "trees", "grass", "flooded_vegetation", "crops", "shrub_and_scrub", "built", "bare", "snow_and_ice")
NODATA = -9999
LandStage = Literal["sources", "pixels", "summary"]


def monthly_windows(end: date, months: int) -> list[tuple[date, date]]:
    windows = []
    for delta in reversed(range(months)):
        year, month = divmod(end.year * 12 + end.month - 1 - delta, 12)
        start = date(year, month + 1, 1)
        windows.append((start, min(end, start.replace(day=monthrange(year, month + 1)[1]))))
    return windows


def optical_bands(image: Any, ee: Any) -> Any:
    clear = image.select("SCL").remap([4, 5, 6], [1, 1, 1], 0)
    values = image.select(["B4", "B3", "B2", "B8", "B11"], ["r", "g", "b", "nir", "swir"]).updateMask(clear)
    ndvi = values.normalizedDifference(["nir", "r"]).rename("ndvi")
    ndmi = values.normalizedDifference(["nir", "swir"]).rename("ndmi")
    water = values.normalizedDifference(["g", "swir"]).gt(0).And(ndvi.lt(0.2)).rename("water")
    return ee.Image.cat([values.select(["r", "g", "b"]), values.select("r").rename("red"), ndvi, ndmi, water]).toFloat()


def monthly_image(ee: Any, optical: Any, cover: Any, area: Any) -> Any:
    def confident_label(image: Any) -> Any:
        confident = image.select(list(COVER_BANDS)).reduce(ee.Reducer.max()).gte(0.55)
        return image.select("label").updateMask(confident).rename("cover").toFloat()

    empty_optical = ee.Image.constant([0] * 7).rename(list(BANDS[:7])).toFloat().selfMask()
    optics = optical.map(lambda image: optical_bands(image, ee)).merge(ee.ImageCollection([empty_optical])).median()
    empty_label = ee.Image.constant(0).rename("cover").toFloat().selfMask()
    labels = cover.map(confident_label).merge(ee.ImageCollection([empty_label])).mode()
    return ee.Image.cat([optics, labels, ee.Image.constant(1).rename("aoi")]).clip(area).toFloat().unmask(NODATA, False)


def build_profile(project: str, request: LandRequest, max_km2: float,
                  progress: Callable[[LandStage], None] | None = None) -> LandBundle:
    area_km2 = validate_aoi(request.aoi, max_km2).area_km2
    grid = Grid.around(request.aoi, GRID_M)
    if grid.width * grid.height > 160_000:
        raise ValueError("Draw a more compact boundary for monthly land observations.")
    client = EarthEngineProvider(project)
    if progress:
        progress("sources")
    ee = client._sdk()
    area = client._area(request.aoi)
    snapshots = []
    bands = []
    metadata = []
    windows = monthly_windows(request.end, request.months)
    for index, (start, end) in enumerate(windows):
        exclusive = str(end + timedelta(days=1))
        optical = (ee.ImageCollection(OPTICAL).filterBounds(area).filterDate(str(start), exclusive)
                   .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 80)).sort("CLOUDY_PIXEL_PERCENTAGE").limit(18))
        cover = ee.ImageCollection(COVER).filterBounds(area).filterDate(str(start), exclusive)
        soil = ee.ImageCollection(SOIL).filterDate(str(start), exclusive).select("sm_surface")
        soil_value = ee.Algorithms.If(soil.size().gt(0), soil.mean().reduceRegion(
            reducer=ee.Reducer.mean(), geometry=area.centroid(5), scale=11000).get("sm_surface", NODATA), NODATA)
        metadata.append(ee.Dictionary({"scenes": optical.reduceColumns(
            ee.Reducer.toList(2), ["system:index", "system:time_start"]).get("list"), "soil": soil_value}))
        bands.append(monthly_image(ee, optical, cover, area).rename([f"{name}_{index}" for name in BANDS]))

    try:
        sources = ee.List(metadata).getInfo()
        if progress:
            progress("pixels")
        rasters = [ee.data.computePixels({"expression": ee.Image.cat(bands[start:start + 4]),
                                         "fileFormat": "NUMPY_NDARRAY", "grid": grid.ee_grid()})
                   for start in range(0, len(bands), 4)]
    except ee.EEException as error:
        raise ProviderError("Earth Engine could not retrieve the monthly observations. Retry or use a smaller boundary or shorter window.") from error

    if progress:
        progress("summary")
    previous: tuple[date, np.ndarray] | None = None
    scenario_cover = None
    scenario_period = None
    for index, ((start, end), source) in enumerate(zip(windows, sources, strict=True)):
        pixels = rasters[index // 4]
        values = {name: pixels[f"{name}_{index}"] for name in BANDS}
        inside = values["aoi"] == 1
        if not inside.any():
            raise ValueError("The boundary is smaller than the land observation grid. Draw a larger area.")
        clear = inside & (values["ndvi"] != NODATA) & (values["ndmi"] != NODATA)
        coverage = clear.sum() / inside.sum()
        classified = inside & (values["cover"] >= 0) & (values["cover"] < len(CLASSES))
        labels = np.where(classified, values["cover"], MISSING_CLASS).astype(np.uint8)
        proportions = {name: round(100 * float((labels == code).sum()) / int(classified.sum()), 2)
                       for code, name in enumerate(CLASSES)} if classified.any() else {}
        if np.isin(labels, MODELED_CLASSES).any() and classified.sum() / inside.sum() >= MIN_CLEAR:
            scenario_cover, scenario_period = labels, start
        image = None
        offset = None
        if clear.any():
            rgb = np.stack([values[name] for name in ("r", "g", "b")], axis=-1)
            rgb = (np.sqrt(np.clip(rgb / 4000, 0, 1)) * 255).astype(np.uint8)
            image = png_url(np.dstack([rgb, clear.astype(np.uint8) * 255]))
        if coverage >= MIN_CLEAR:
            red = np.where(clear, values["red"], np.nan)
            if previous is not None:
                offset = image_offset(previous[1], red, previous[0])
            previous = (start, red)
        soil = source.get("soil")
        snapshots.append(LandObservation(
            start=start, end=end, scenes=[SceneDate(id=f"{OPTICAL}/{key}", acquired_at=datetime.fromtimestamp(timestamp / 1000, UTC))
                                          for key, timestamp in sorted(source.get("scenes") or [], key=lambda row: row[1])],
            clear_pct=round(100 * float(coverage), 2),
            ndvi=round(float(values["ndvi"][clear].mean()), 3) if coverage >= MIN_CLEAR else None,
            ndmi=round(float(values["ndmi"][clear].mean()), 3) if coverage >= MIN_CLEAR else None,
            mapped_water_pct=round(100 * float((values["water"][clear] > .5).mean()), 2) if coverage >= MIN_CLEAR else None,
            soil_moisture_pct=round(100 * soil, 2) if soil is not None and 0 <= soil <= 1 else None,
            land_cover_pct=proportions, classified_pct=round(100 * float(classified.sum()) / int(inside.sum()), 2),
            image_offset=offset, image=image,
        ))
    return LandBundle(LandProfile(id=uuid4().hex, title="Satellite land observations", aoi=request.aoi, area_km2=area_km2,
                                  observations=snapshots, scenario_period=scenario_period), scenario_cover)
