import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import box

from backend.app.pipeline.raster import CRS, Grid, RasterStack
from validation.balasore import compare


def test_comparison_excludes_pixels_without_shared_coverage_and_weights_areas():
    grid = Grid(0, 20, 4, 2, 10)
    to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    region = box(*to_lonlat.transform_bounds(0, 0, 30, 20))
    flood = box(*to_lonlat.transform_bounds(10, 0, 20, 20))
    pre = np.zeros((2, 4))
    post = np.array([[0, 0, 0, 0], [0, 0, np.nan, 0]])
    area = np.array([[100, 200, 100, 300], [400, 300, 600, 100]])
    stack = RasterStack(grid, pre, post, np.ones((2, 4), dtype=bool), area, pre, pre, None)
    prediction = np.array([[True, True, False, True], [False, False, True, True]])

    metrics = compare(stack, prediction, region, flood)

    assert metrics["eligible_ha"] == pytest.approx(0.11)
    assert metrics["outside_reference_ha"] == pytest.approx(0.04)
    assert metrics["missing_radar_inside_reference_ha"] == pytest.approx(0.06)
    assert metrics["true_positive_ha"] == pytest.approx(0.02)
    assert metrics["false_positive_ha"] == pytest.approx(0.01)
    assert metrics["false_negative_ha"] == pytest.approx(0.03)
    assert metrics["true_negative_ha"] == pytest.approx(0.05)
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == pytest.approx(0.4)
    assert metrics["iou"] == pytest.approx(1 / 3)
    assert metrics["f1"] == pytest.approx(0.5)

    empty = compare(stack, np.zeros_like(prediction), region, box(0, 0, 0, 0))
    assert all(empty[key] is None for key in ("precision", "recall", "iou", "f1"))
