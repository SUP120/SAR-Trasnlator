from fastapi.testclient import TestClient
from pyproj import Transformer
from pytest import approx
from shapely.geometry import Polygon

from backend.app.config import Settings
from backend.app.main import create_app

RING = [(91.65, 26.16), (91.69, 26.16), (91.69, 26.19), (91.65, 26.19), (91.65, 26.16)]


def post_area(client: TestClient, *rings: list[tuple[float, float]]):
    return client.post("/api/aois/validate", json={"type": "Polygon", "coordinates": rings})


def test_health_distinguishes_service_from_provider_availability():
    client = TestClient(create_app(Settings(100, earth_engine_configured=True)))
    assert client.get("/api/health").json() == {
        "status": "ok",
        "max_aoi_km2": 100.0,
        "earth_engine": "unverified",
        "analysis_available": False,
    }


def test_area_matches_a_local_equal_area_projection_within_one_percent():
    reference = Transformer.from_crs(
        "EPSG:4326", "+proj=laea +lat_0=26.175 +lon_0=91.67 +ellps=WGS84", always_xy=True,
    )
    expected = Polygon([reference.transform(*point) for point in RING]).area / 1_000_000
    client = TestClient(create_app(Settings()))
    response = post_area(client, RING)
    assert response.status_code == 200
    assert response.json()["area_km2"] == approx(expected, rel=0.01)


def test_hole_is_subtracted_independently_of_winding():
    hole = [(91.66, 26.17), (91.67, 26.17), (91.67, 26.18), (91.66, 26.18), (91.66, 26.17)]
    client = TestClient(create_app(Settings()))
    full_area = post_area(client, RING).json()["area_km2"]
    hole_area = post_area(client, hole).json()["area_km2"]
    assert post_area(client, RING, hole).json()["area_km2"] == approx(full_area - hole_area)


def test_self_intersection_is_rejected():
    client = TestClient(create_app(Settings()))
    response = post_area(client, [RING[index] for index in (0, 2, 1, 3, 0)])
    assert response.status_code == 422
    assert "crossing edges" in response.json()["detail"]


def test_configured_area_limit_is_enforced():
    client = TestClient(create_app(Settings(max_aoi_km2=10)))
    response = post_area(client, RING)
    assert response.status_code == 422
    assert "10 km² limit" in response.json()["detail"]


def test_open_ring_and_out_of_range_coordinates_are_rejected():
    client = TestClient(create_app(Settings()))
    assert "Close all polygon rings" in post_area(client, RING[:-1]).json()["detail"]
    invalid_coordinate = [(181, 26.16), *RING[1:-1], (181, 26.16)]
    assert post_area(client, invalid_coordinate).status_code == 422


def test_rejects_coordinates_that_overflow_to_infinity():
    client = TestClient(create_app(Settings()))
    response = client.post(
        "/api/aois/validate",
        content='{"type":"Polygon","coordinates":[[[1e309,26],[91,26],[91,27],[1e309,26]]]}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "finite_number"
