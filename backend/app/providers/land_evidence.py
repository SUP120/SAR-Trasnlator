from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..aoi import AoiPolygon
from ..land import GRID_M, LandProfile, RecordedRain, SceneDate, png_url
from ..land_evidence import (HistoryEvidence, ImageEvidence, InspectionEvidence, MIN_GREENNESS_DROP,
                             MIN_PATCH_CELLS, PlotEvidence, find_patches)
from ..pipeline.raster import Grid
from .base import ProviderError
from .earth_engine import DEM, EarthEngineProvider
from .land_optical import BANDS, COVER, NODATA, OPTICAL, monthly_image

RAIN = "UCSB-CHG/CHIRPS/DAILY"
WATER = "JRC/GSW1_4/GlobalSurfaceWater"
LANDSAT_5 = "LANDSAT/LT05/C02/T1_L2"
LANDSAT_8 = "LANDSAT/LC08/C02/T1_L2"
LANDSAT_9 = "LANDSAT/LC09/C02/T1_L2"


def bounded_grid(aoi: AoiPolygon) -> Grid:
    grid = Grid.around(aoi, GRID_M)
    if grid.width * grid.height > 160_000:
        raise ValueError("Use a more compact boundary for this satellite comparison.")
    return grid


def pixels(ee: Any, image: Any, grid: Grid) -> NDArray:
    try:
        return ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": grid.ee_grid()})
    except ee.EEException as error:
        raise ProviderError("Earth Engine could not load the satellite evidence. Try again shortly.") from error


def scene_dates(ee: Any, collection: Any) -> list[SceneDate]:
    try:
        rows = collection.reduceColumns(ee.Reducer.toList(2), ["source_id", "system:time_start"]).getInfo()["list"]
    except ee.EEException as error:
        raise ProviderError("Earth Engine could not load the satellite image dates.") from error
    return [SceneDate(id=key, acquired_at=datetime.fromtimestamp(timestamp / 1000, UTC))
            for key, timestamp in sorted(rows or [], key=lambda row: row[1])]


def preview(start: date, end: date, samples: NDArray, scenes: list[SceneDate], brightness: float) -> ImageEvidence:
    inside = samples["aoi"] == 1
    clear = inside & (samples["r"] != NODATA)
    rgb = np.stack([samples[name] for name in ("r", "g", "b")], axis=-1)
    rgb = (255 * np.sqrt(np.clip(rgb / brightness, 0, 1))).astype(np.uint8)
    return ImageEvidence(start=start, end=end, clear_pct=round(100 * float(clear.sum()) / max(1, int(inside.sum())), 2),
                         image=png_url(np.dstack([rgb, clear.astype(np.uint8) * 255])), scenes=scenes)


def build_inspection(project: str, profile: LandProfile) -> InspectionEvidence:
    recent = next((item for item in reversed(profile.observations) if item.ndvi is not None), None)
    if recent is None or recent.start.year < 2021:
        raise ValueError("Choose a recent month with clear imagery and at least three prior Sentinel-2 seasons.")
    grid = bounded_grid(profile.aoi)
    client = EarthEngineProvider(project)
    ee, area = client._sdk(), client._area(profile.aoi)
    previews, vegetation, crop_masks = [], [], []
    for year in range(recent.start.year - 3, recent.start.year + 1):
        start = recent.start.replace(year=year)
        end = start.replace(day=min(recent.end.day, monthrange(year, start.month)[1]))
        exclusive = str(end + timedelta(days=1))
        optical = (ee.ImageCollection(OPTICAL).filterBounds(area).filterDate(str(start), exclusive)
                   .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 80)).sort("CLOUDY_PIXEL_PERCENTAGE").limit(18)
                   .map(lambda image: image.set("source_id", ee.String(f"{OPTICAL}/").cat(image.getString("system:index")))))
        cover = ee.ImageCollection(COVER).filterBounds(area).filterDate(str(start), exclusive)
        image = monthly_image(ee, optical, cover, area).select([name for name in BANDS if name in {"r", "g", "b", "ndvi", "cover", "aoi"}])
        data = pixels(ee, image, grid)
        inside = data["aoi"] == 1
        previews.append(preview(start, end, data, scene_dates(ee, optical), 4000))
        vegetation.append(np.where(inside & (data["ndvi"] != NODATA), data["ndvi"], np.nan))
        crop_masks.append(data["cover"] == 4)

    historical = np.stack(vegetation[:-1])
    sufficient = np.isfinite(historical).sum(axis=0) >= 2
    baseline = np.full(inside.shape, np.nan)
    baseline[sufficient] = np.nanmedian(historical[:, sufficient], axis=0)
    reference_crops = np.any(np.stack(crop_masks), axis=0)
    shared, flagged, patches = find_patches(grid, inside, vegetation[-1], baseline, reference_crops)
    rgba = np.zeros((*flagged.shape, 4), dtype=np.uint8)
    rgba[flagged] = (242, 118, 25, 175)
    return InspectionEvidence(earlier=previews[:-1], recent=previews[-1], shared_pct=shared, grid_m=GRID_M,
                              min_drop=MIN_GREENNESS_DROP, min_cells=MIN_PATCH_CELLS,
                              highlight=png_url(rgba), patches=patches)


def build_history(project: str, profile: LandProfile) -> HistoryEvidence:
    latest = profile.observations[-1].end
    # Compare the same three complete calendar months in years thirty years apart.
    anchor = latest + timedelta(days=1) if latest.day == monthrange(latest.year, latest.month)[1] else latest
    grid = bounded_grid(profile.aoi)
    client = EarthEngineProvider(project)
    ee, area = client._sdk(), client._area(profile.aoi)
    comparisons = []
    for year, sources in ((anchor.year - 30, (LANDSAT_5,)), (anchor.year, (LANDSAT_8, LANDSAT_9))):
        end = date(year, anchor.month, 1)
        start_year, start_month = divmod(year * 12 + end.month - 4, 12)
        start = date(start_year, start_month + 1, 1)
        collection = ee.ImageCollection([])
        for source in sources:
            bands = ["SR_B3", "SR_B2", "SR_B1"] if source == LANDSAT_5 else ["SR_B4", "SR_B3", "SR_B2"]

            def prepare(image: Any) -> Any:
                clear = image.select("QA_PIXEL").bitwiseAnd(63).eq(0).And(image.select("QA_RADSAT").eq(0))
                return (image.select(bands, ["r", "g", "b"]).multiply(0.0000275).add(-0.2).toFloat()
                        .updateMask(clear).set({
                            "source_id": ee.String(f"{source}/").cat(image.getString("system:index")),
                            "system:time_start": image.get("system:time_start"),
                        }))

            scenes = ee.ImageCollection(source).filterBounds(area).filterDate(str(start), str(end))
            collection = collection.merge(scenes.sort("CLOUD_COVER").limit(24).map(prepare))
        empty = ee.Image.constant([0, 0, 0]).rename(["r", "g", "b"]).toFloat().selfMask()
        rgb = collection.merge(ee.ImageCollection([empty])).median()
        image = ee.Image.cat([rgb, ee.Image.constant(1).rename("aoi")]).clip(area).toFloat().unmask(NODATA, False)
        evidence = preview(start, end - timedelta(days=1), pixels(ee, image, grid), scene_dates(ee, collection), .32)
        if evidence.clear_pct < 20:
            raise ValueError(f"Too little clear Landsat imagery for {start:%b %Y} to {evidence.end:%b %Y}. Try a different end date.")
        comparisons.append(evidence)
    return HistoryEvidence(earlier=comparisons[0], recent=comparisons[1], grid_m=GRID_M)


def build_plot_evidence(project: str, aoi: AoiPolygon) -> PlotEvidence:
    grid = bounded_grid(aoi)
    client = EarthEngineProvider(project)
    ee, area = client._sdk(), client._area(aoi)
    dem = ee.ImageCollection(DEM).filterBounds(area).select("DEM")
    slope = ee.Terrain.slope(dem.mosaic().setDefaultProjection(dem.first().projection()))
    observed = ee.Image("JRC/GSW1_4/Metadata").select("valid_obs").unmask(0)
    water = ee.Image(WATER).select("max_extent").bitwiseAnd(1).unmask(0)
    image = ee.Image.cat([slope, observed, water, ee.Image.constant(1).rename("aoi")])
    samples = pixels(ee, image.clip(area).toFloat().unmask(NODATA, False), grid)
    inside = samples["aoi"] == 1
    valid_water = inside & (samples["valid_obs"] > 0)
    valid_slope = inside & (samples["slope"] >= 0)
    total = max(1, int(inside.sum()))
    return PlotEvidence(
        water_area_pct=round(100 * float(samples["max_extent"][valid_water].mean()), 2) if valid_water.any() else None,
        water_coverage_pct=round(100 * int(valid_water.sum()) / total, 2),
        average_slope_deg=round(float(samples["slope"][valid_slope].mean()), 2) if valid_slope.any() else None,
        slope_coverage_pct=round(100 * int(valid_slope.sum()) / total, 2),
    )


def load_rain(project: str, aoi: AoiPolygon, start: date, days: int) -> RecordedRain:
    client = EarthEngineProvider(project)
    ee, area = client._sdk(), client._area(aoi)
    end = start + timedelta(days=days)
    images = ee.ImageCollection(RAIN).filterDate(str(start), str(end)).select("precipitation")
    try:
        columns, *rows = images.getRegion(area.centroid(5), 5566).getInfo()
    except ee.EEException as error:
        raise ProviderError("Earth Engine could not retrieve the CHIRPS rainfall series.") from error
    time_col, rain_col = columns.index("time"), columns.index("precipitation")
    by_date = {datetime.fromtimestamp(row[time_col] / 1000, UTC).date(): row[rain_col] for row in rows}
    values = [by_date.get(start + timedelta(days=day)) for day in range(days)]
    if any(value is None or not np.isfinite(value) or value < 0 for value in values):
        raise ValueError("Rainfall is missing for some days in this window. Choose an earlier monsoon year.")
    return RecordedRain(start=start, daily_mm=[round(float(value), 3) for value in values if value is not None], source=RAIN)
