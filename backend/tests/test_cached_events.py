from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.cached_events import EVENTS_DIRECTORY, EventCatalog
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.providers.earth_engine import EarthEngineProvider

SLUG = "north-guwahati-2022"


@pytest.mark.parametrize(("slug", "title", "first_before", "after", "flood_ha"), [
    (SLUG, "North Guwahati, June 2022", "2022-06-04", "2022-06-16", 358.02),
    ("central-gujarat-2024", "Central Gujarat, August 2024", "2024-07-23", "2024-08-28", 384.84),
    ("balasore-2024", "Balasore, October 2024", "2024-08-29", "2024-10-28", 554.95),
])
def test_cached_observations_and_reports_work_offline_and_survive_restart(monkeypatch, slug, title, first_before, after, flood_ha):
    def unexpected_live_access(_provider):
        raise AssertionError("A cached event attempted to access Earth Engine.")

    monkeypatch.setattr(EarthEngineProvider, "_sdk", unexpected_live_access)
    with TestClient(create_app(Settings())) as api:
        assert api.get("/api/health").json()["analysis_available"] is False
        catalog = api.get("/api/demo/events").json()
        assert any(event["source"] == "synthetic" for event in catalog)
        assert {"slug": slug, "source": "cached", "title": title} in catalog
        event = api.get(f"/api/demo/events/{slug}")
        assert event.status_code == 200
        snapshot = event.json()
        identifier = snapshot["id"]
        result = snapshot["result"]
        assert snapshot["status"] == "done"
        assert result["source"] == "earth_engine"
        assert result["cached_event"]["slug"] == slug
        assert result["stats"]["flood_ha"] == flood_ha
        assert result["quality"]["overall"] == "Low"
        assert result["pre"][0]["acquired_at"][:10] == first_before
        assert [observation["acquired_at"][:10] for observation in result["post"]] == [after]
        assert api.get("/api/demo/events/unknown-event").status_code == 404

    with TestClient(create_app(Settings())) as restarted:
        assert restarted.get(f"/api/analyses/{identifier}").json() == snapshot
        for name, path in result["layers"].items():
            layer = restarted.get(f"/api/{path}")
            assert layer.status_code == 200
            assert layer.content == (EVENTS_DIRECTORY / slug / f"{name}.png").read_bytes()

        for language in ("en", "hi"):
            explanation = restarted.post(f"/api/analyses/{identifier}/explain?lang={language}")
            assert explanation.status_code == 200
            assert f"{flood_ha:.2f}" in explanation.json()["summary"]
            response = restarted.get(f"/api/analyses/{identifier}/report.pdf?lang={language}")
            assert response.status_code == 200
            assert f"{slug}-{language}.pdf" in response.headers["Content-Disposition"]
            pages = PdfReader(BytesIO(response.content)).pages
            assert len(pages) == 1 and len(pages[0].images) == 3
            assert title in pages[0].extract_text()
            if language == "en":
                assert "CACHED SENTINEL-1 OBSERVATIONS" in pages[0].extract_text()


def test_incomplete_event_is_omitted_from_the_catalog(tmp_path, caplog):
    incomplete = tmp_path / "incomplete-example"
    incomplete.mkdir()
    (incomplete / "event.json").write_bytes((EVENTS_DIRECTORY / SLUG / "event.json").read_bytes())

    assert not EventCatalog(tmp_path).by_slug
    assert "Skipping historical event incomplete-example" in caplog.text
