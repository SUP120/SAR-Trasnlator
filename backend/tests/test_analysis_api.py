from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.providers.synthetic import EXAMPLE_AOI


def test_synthetic_flow_serves_results_rasters_bilingual_explanations_and_reports():
    api = TestClient(create_app(Settings()))
    assert api.get("/api/demo/events").json()[0]["source"] == "synthetic"
    response = api.post("/api/analyses", json={"source": "synthetic"})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    id_ = response.json()["id"]
    result = api.get(f"/api/analyses/{id_}").json()
    assert result["status"] == "done", result
    payload = result["result"]
    assert payload["source"] == "synthetic"
    assert 0 < payload["stats"]["flood_pct_of_aoi"] < 100
    for layer in payload["layers"].values():
        raster = api.get(f"/api/{layer}")
        assert raster.status_code == 200
        with Image.open(BytesIO(raster.content)) as image:
            assert image.mode == "RGBA"
            assert 0 < image.width <= 601 and 0 < image.height <= 601

    for language in ("en", "hi"):
        explanation = api.post(f"/api/analyses/{id_}/explain?lang={language}").json()
        assert explanation["source"] == "template"
        assert "2020-06-10" in explanation["summary"]
        assert f'{payload["stats"]["flood_ha"]:.2f}' in explanation["summary"]
        report = api.get(f"/api/analyses/{id_}/report.pdf?lang={language}")
        assert report.status_code == 200
        assert "synthetic" in report.headers["Content-Disposition"]
        reader = PdfReader(BytesIO(report.content))
        assert len(reader.pages) == 1
        assert len(reader.pages[0].images) == 3
        if language == "en":
            assert "SYNTHETIC EXAMPLE" in reader.pages[0].extract_text()
        else:
            assert any("NotoSansDevanagari" in str(font.get_object()["/BaseFont"])
                       for font in reader.pages[0]["/Resources"]["/Font"].values())
            assert "VV/VH" in reader.pages[0].extract_text()
            assert "SAR TRANSLATOR" in reader.pages[0].extract_text()


def test_live_job_fails_explicitly_when_project_is_not_configured():
    api = TestClient(create_app(Settings()))
    result = api.post("/api/analyses", json={"source": "earth_engine", "aoi": EXAMPLE_AOI.model_dump(mode="json"),
                                             "window": {"kind": "preset", "days": 30}})
    assert result.status_code == 503
    assert "Earth Engine" in result.json()["detail"]
