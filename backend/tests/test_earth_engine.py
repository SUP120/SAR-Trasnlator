from datetime import date

import pytest
from pyproj import CRS

from backend.app.aoi import AoiPolygon
from backend.app.pipeline.raster import Grid
from backend.app.providers.earth_engine import EarthEngineProvider


def test_provider_initializes_earth_engine_before_configuring_transport(monkeypatch):
    ee = pytest.importorskip("ee")
    calls = []

    monkeypatch.setattr(ee, "Initialize", lambda *, project: calls.append(("initialize", project)))
    monkeypatch.setattr(ee.data, "setDeadline", lambda milliseconds: calls.append(("deadline", milliseconds)))
    monkeypatch.setattr(ee.data, "setMaxRetries", lambda retries: calls.append(("retries", retries)))

    provider = EarthEngineProvider("test-project")
    assert provider._sdk() is ee
    assert provider._sdk() is ee
    assert calls == [("initialize", "test-project"), ("deadline", 35_000), ("retries", 1)]


def test_scene_id_is_serialized_as_explicit_metadata(monkeypatch):
    ee = pytest.importorskip("ee")
    ee_test = pytest.importorskip("ee.apitestcase")
    monkeypatch.setattr(ee.data, "_install_cloud_api_resource", lambda: None)
    monkeypatch.setattr(ee.data, "getAlgorithms", ee_test.GetAlgorithms)
    area = AoiPolygon(type="Polygon", coordinates=[[
        (91.65, 26.16), (91.69, 26.16), (91.69, 26.19), (91.65, 26.19), (91.65, 26.16),
    ]])

    def compute_value(expression):
        serialized = expression.serialize()
        assert '"scene_index"' in serialized and '"system:index"' in serialized
        return {"features": [{"geometry": area.model_dump(mode="json"), "properties": {
            "scene_index": "fixture-scene-id",
            "system:time_start": 1654343829000,
            "platform_number": "A",
            "orbitProperties_pass": "ASCENDING",
            "relativeOrbitNumber_start": 41,
            "instrumentMode": "IW",
            "transmitterReceiverPolarisation": ["VV", "VH"],
        }}]}

    monkeypatch.setattr(ee.data, "computeValue", compute_value)
    ee.Initialize(None, project="test-project")
    try:
        provider = EarthEngineProvider("test-project")
        provider._ee = ee
        scenes = provider.scenes(area, date(2022, 6, 4), date(2022, 6, 5))
        assert [scene.id for scene in scenes] == ["COPERNICUS/S1_GRD/fixture-scene-id"]
    finally:
        ee.Reset()


def test_earth_engine_grid_uses_an_equivalent_equal_area_wkt():
    grid = Grid(west=500_000, north=600_000, width=25, height=12, scale_m=10)
    pixel_grid = grid.ee_grid()
    assert "crsCode" not in pixel_grid
    assert CRS.from_wkt(pixel_grid["crsWkt"]).equals(CRS.from_epsg(6933), ignore_axis_order=True)
    assert pixel_grid["dimensions"] == {"width": 25, "height": 12}
    assert pixel_grid["affineTransform"] == {"scaleX": 10, "scaleY": -10, "translateX": 500_000, "translateY": 600_000}
