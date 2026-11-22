"""Replay the cached Balasore analysis and compare it with the JAXA flood proxy."""

import argparse
import json
from datetime import date
from hashlib import sha256
from io import BytesIO
from math import isclose
from os import getenv
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from shapely import intersects_xy, make_valid
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from backend.app.analysis import METHOD_VERSION, Observation
from backend.app.cached_events import EVENTS_DIRECTORY, load_event
from backend.app.pipeline.pairing import Pair, Scene
from backend.app.pipeline.raster import Grid, RasterStack, detect, project, render_layers
from backend.app.providers.earth_engine import EarthEngineProvider

REFERENCE_DATE = date(2024, 10, 26)
REFERENCE_SHA256 = "1294df75e3ad3f44687dc6f594ca3691bdcaa3b194c46c50ca9f2e35f562a793"
REFERENCE_PREFIX = "2024-00069-WLD_202410260643"


def read_reference(path: Path, aoi: BaseGeometry) -> tuple[BaseGeometry, BaseGeometry]:
    if sha256(path.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("Use the original JAXA archive linked in validation/results.md.")
    with ZipFile(path) as archive:
        region, flood = (
            json.loads(archive.read(f"JAXA_20241026_FPM_ALOS2_India_FLDEXT/{REFERENCE_PREFIX}_{kind}.geojson"))
            for kind in ("REGION", "FLDEXT")
        )

    def clip(collection: dict) -> BaseGeometry:
        geometries = [shape(feature["geometry"]) for feature in collection["features"]]
        return unary_union([make_valid(geometry).intersection(aoi) for geometry in geometries if geometry.intersects(aoi)])

    return clip(region), clip(flood)


def compare(
    stack: RasterStack, prediction: NDArray[np.bool_], region: BaseGeometry, flood: BaseGeometry,
) -> dict[str, float | None]:
    grid = stack.grid
    x = grid.west + (np.arange(grid.width) + 0.5) * grid.scale_m
    y = grid.north - (np.arange(grid.height) + 0.5) * grid.scale_m
    in_region = intersects_xy(project(region), x[None, :], y[:, None])
    mapped = intersects_xy(project(flood), x[None, :], y[:, None])
    radar_valid = np.isfinite(stack.pre_vv) & np.isfinite(stack.post_vv)
    eligible = stack.aoi & radar_valid & in_region

    def hectares(mask: NDArray[np.bool_]) -> float:
        return float(stack.pixel_area[mask].sum(dtype=np.float64)) / 10_000

    def ratio(numerator: float, denominator: float) -> float | None:
        return numerator / denominator if denominator else None

    tp = hectares(eligible & prediction & mapped)
    fp = hectares(eligible & prediction & ~mapped)
    fn = hectares(eligible & ~prediction & mapped)
    tn = hectares(eligible & ~prediction & ~mapped)
    return {
        "aoi_ha": hectares(stack.aoi),
        "eligible_ha": hectares(eligible),
        "eligible_fraction": ratio(hectares(eligible), hectares(stack.aoi)),
        "outside_reference_ha": hectares(stack.aoi & ~in_region),
        "missing_radar_inside_reference_ha": hectares(stack.aoi & in_region & ~radar_valid),
        "mapped_flood_ha": tp + fn,
        "predicted_flood_ha": tp + fp,
        "true_positive_ha": tp,
        "false_positive_ha": fp,
        "false_negative_ha": fn,
        "true_negative_ha": tn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "iou": ratio(tp, tp + fp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Path to the public JAXA ALOS-2 reference ZIP")
    args = parser.parse_args()
    project_id = getenv("EE_PROJECT_ID", "").strip()
    if not project_id:
        parser.error("Set EE_PROJECT_ID and authenticate Earth Engine before replaying the analysis.")

    event = load_event(EVENTS_DIRECTORY / "balasore-2024")
    result = event.snapshot.result
    if result is None or result.method_version != METHOD_VERSION:
        raise ValueError("The saved result must use the current radar screening method.")
    aoi = shape(result.aoi.model_dump())
    region, flood = read_reference(args.archive, aoi)
    if region.is_empty or flood.is_empty:
        raise ValueError("The reference region and mapped flood must overlap the Balasore study area.")

    def scene(observation: Observation) -> Scene:
        # The provider reads the saved scene IDs for pixels. The comparison uses actual finite pixel coverage.
        return Scene(observation.id, observation.acquired_at, observation.platform, result.geometry, aoi)

    pair = Pair(tuple(map(scene, result.pre)), tuple(map(scene, result.post)), result.footprint_coverage_pct / 100)
    grid = Grid.around(result.aoi, result.parameters.scale_m)
    stack = EarthEngineProvider(project_id).pixels(result.aoi, pair, grid, result.parameters)
    detection = detect(stack, result.parameters)
    if not isclose(detection.stats["flood_ha"], result.stats.flood_ha, abs_tol=1e-6):
        raise ValueError("The replayed flood area differs from the cached result.")
    rendered = render_layers(stack, detection.flood)
    with (Image.open(BytesIO(rendered.pngs["change"])) as replay,
          Image.open(BytesIO(event.layers.pngs["change"])) as cached):
        if not np.array_equal(np.asarray(replay), np.asarray(cached)):
            raise ValueError("The replayed change PNG differs from the cached result.")

    print(json.dumps({
        "case": event.slug,
        "method": result.method_version,
        "grid_m": grid.scale_m,
        "reference_date": str(REFERENCE_DATE),
        "pre_utc": [item.acquired_at.isoformat() for item in result.pre],
        "post_utc": [item.acquired_at.isoformat() for item in result.post],
        "cache_change_png_exact_match": True,
        **compare(stack, detection.flood, region, flood),
    }, indent=2))


if __name__ == "__main__":
    main()
