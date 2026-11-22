"""Check authenticated Earth Engine access and print Sentinel-1 scene metadata as JSON."""

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from os import getenv

SENTINEL = "COPERNICUS/S1_GRD"
SCENE_PROPERTIES = (
    "system:index",
    "system:time_start",
    "platform_number",
    "orbitProperties_pass",
    "relativeOrbitNumber_start",
    "instrumentMode",
    "transmitterReceiverPolarisation",
)
DATASETS = (
    ("JRC/GSW1_4/GlobalSurfaceWater", False, {"occurrence", "seasonality"}),
    ("COPERNICUS/DEM/GLO30_2024_1", True, {"DEM"}),
    ("ESA/WorldCover/v200", True, {"Map"}),
    ("MERIT/Hydro/v1_0_1", False, {"hnd"}),
)


def timestamp(milliseconds: int | None) -> str | None:
    return datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat() if milliseconds is not None else None


def probe(ee, project: str, bounds: list[float], start: date, end: date) -> dict:
    ee.Initialize(project=project)
    ee.data.setDeadline(30_000)
    collection = ee.ImageCollection(SENTINEL)
    today = datetime.now(UTC).date()
    recent = collection.filterDate((today - timedelta(days=30)).isoformat(), (today + timedelta(days=1)).isoformat())
    latest_platform_dates = {
        platform: timestamp(milliseconds)
        for platform in ("A", "B", "C", "D")
        if (milliseconds := recent.filter(ee.Filter.eq("platform_number", platform)).aggregate_max("system:time_start").getInfo()) is not None
    }
    area = ee.Geometry.Rectangle(bounds)
    candidate_scenes = (collection.filterBounds(area)
        .filterDate(start.isoformat(), end.isoformat())
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
    rows = candidate_scenes.sort("system:time_start").limit(200).reduceColumns(
        ee.Reducer.toList(len(SCENE_PROPERTIES)), list(SCENE_PROPERTIES),
    ).get("list").getInfo()
    scenes = [dict(zip(SCENE_PROPERTIES, row, strict=True)) for row in rows]
    for scene in scenes:
        scene["acquired_at_utc"] = timestamp(scene.pop("system:time_start"))

    datasets = {}
    for dataset_id, is_collection, expected_bands in DATASETS:
        try:
            image = ee.Image(ee.ImageCollection(dataset_id).filterBounds(area).first()) if is_collection else ee.Image(dataset_id)
            bands = image.bandNames().getInfo()
            datasets[dataset_id] = {"bands": bands, "missing_expected_bands": sorted(expected_bands - set(bands))}
        except ee.EEException as error:
            datasets[dataset_id] = {"error": type(error).__name__}

    return {
        "collection": SENTINEL,
        "collection_latest_acquisition_utc": timestamp(recent.aggregate_max("system:time_start").getInfo()),
        "latest_platform_acquisitions_last_30_days_utc": latest_platform_dates,
        "first_aoi_scene_bands": ee.Image(candidate_scenes.first()).bandNames().getInfo() if scenes else [],
        "aoi": {"bbox": bounds, "start_inclusive": str(start), "end_exclusive": str(end)},
        "scene_count_total": candidate_scenes.size().getInfo(),
        "scenes": scenes,
        "auxiliary_datasets": datasets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, type=float, default=[91.65, 26.16, 91.69, 26.19],
                        metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 5, 15))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2022, 7, 15), help="Exclusive UTC end date")
    args = parser.parse_args()
    west, south, east, north = args.bbox
    if not all(map(isfinite, args.bbox)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        parser.error("bbox must be a finite, ordered longitude/latitude rectangle")
    if args.start >= args.end:
        parser.error("the start date must precede the end date")

    project = getenv("EE_PROJECT_ID", "").strip()
    if not project:
        print("Earth Engine probe skipped because EE_PROJECT_ID is unset.", file=sys.stderr)
        return 2
    try:
        import ee
        from google.auth.exceptions import GoogleAuthError
    except ImportError:
        print("Install backend/requirements-earth-engine.txt before running the probe.", file=sys.stderr)
        return 2

    try:
        results = probe(ee, project, args.bbox, args.start, args.end)
    except (ee.EEException, GoogleAuthError, OSError) as error:
        print(f"Earth Engine probe failed ({type(error).__name__}). Check authentication, project access and connectivity.", file=sys.stderr)
        return 1
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
