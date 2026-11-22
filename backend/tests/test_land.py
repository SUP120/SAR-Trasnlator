import json
from datetime import date
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app import land_narrative
from backend.app.api.land import DEMO_DIRECTORY, read_demos
from backend.app.api import land as land_routes
from backend.app.config import Settings
from backend.app.land import image_offset
from backend.app.land_evidence import find_patches
from backend.app.main import create_app
from backend.app.pipeline.raster import Grid
from backend.app.providers import land_optical


def test_image_offsets_use_correlated_texture_and_reject_flat_images():
    # Synthetic fixture with a translation of one 30 m grid cell east and north.
    rng = np.random.default_rng(33)
    before = rng.normal(2100, 250, (56, 56))
    after = np.full_like(before, np.nan)
    after[:-1, 1:] = before[1:, :-1]
    start = date(2025, 2, 1)
    offset = image_offset(before, after, start)
    assert offset is not None
    assert (offset.east_m, offset.north_m, offset.from_period) == (30, 30, start)
    assert image_offset(np.full_like(before, 1600), after, start) is None


def test_month_windows_keep_inclusive_end_and_leap_days():
    assert land_optical.monthly_windows(date(2024, 3, 10), 3) == [
        (date(2024, 1, 1), date(2024, 1, 31)), (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 3, 1), date(2024, 3, 10)),
    ]


def test_inspection_only_flags_connected_crop_patches_with_shared_imagery():
    # Synthetic equal-area cells with one four-cell drop and one isolated drop.
    grid = Grid(0, 0, 8, 6, 30)
    inside = np.ones((6, 8), dtype=bool)
    reference = np.full(inside.shape, .70)
    recent = reference.copy()
    recent[1:3, 2:4] = .44
    recent[5, 7] = .35
    recent[0, 0] = np.nan
    crops = np.ones_like(inside)
    coverage, flags, patches = find_patches(grid, inside, recent, reference, crops)
    assert coverage == 97.92
    assert flags.sum() == 4 and len(patches) == 1
    assert patches[0].hectares == .36
    assert (patches[0].earlier_greenness, patches[0].recent_greenness) == (.70, .44)
    assert find_patches(grid, inside, recent, reference, ~crops)[2] == []


@pytest.mark.parametrize(("identifier", "rain_total"), [("punjab-farmland", 201.713), ("thar-dryland", 67.816)])
def test_archived_evidence_uses_real_scenes_and_daily_rainfall_offline(identifier, rain_total):
    with TestClient(create_app(Settings())) as api:
        base = f"/api/land/analyses/{identifier}"
        inspection = api.get(f"{base}/inspection").json()
        assert len(inspection["earlier"]) == 3 and inspection["recent"]["scenes"]
        assert inspection["patches"] and inspection["shared_pct"] >= 20
        history = api.get(f"{base}/history").json()
        assert history["earlier"]["start"] == "1995-01-01" and history["recent"]["start"] == "2025-01-01"
        assert history["earlier"]["scenes"][0]["id"].startswith("LANDSAT/LT05/")
        assert history["earlier"]["image"] != history["recent"]["image"]
        facts = api.get(f"{base}/plot").json()
        assert facts["average_slope_deg"] > 0 and facts["water_coverage_pct"] == 100
        inputs = {"days": 28, "rain_mm_week": 0, "demand_mm_day": 3, "storage_capacity_mm": 100, "initial_storage_pct": 50}
        response = api.post(f"{base}/monsoon/2024", json=inputs)
        assert response.status_code == 200, response.text
        replay = response.json()
        daily = replay["recorded_rain"]["daily_mm"]
        assert len(daily) == 28 and sum(daily) == pytest.approx(rain_total)
        assert replay["frames"][1]["terrain_storage_pct"]
        manual = api.post(f"{base}/scenario", json={**inputs, "rain_mm_week": sum(daily) / 4}).json()
        assert replay["frames"][1]["image"] != manual["frames"][1]["image"]


@pytest.mark.parametrize(("identifier", "cover"), [("punjab-farmland", "Crops"), ("thar-dryland", "Bare ground")])
def test_real_land_demos_generate_reports_and_distinct_scenarios_without_earth_engine(identifier, cover):
    with TestClient(create_app(Settings())) as api:
        listing = api.get("/api/land/catalog").json()["demos"]
        assert {item["terrain"] for item in listing} == {"farmland", "dryland"}
        profile = api.get(f"/api/land/analyses/{identifier}").json()
        assert len(profile["observations"]) == 6
        assert profile["narrative"]["source"] == "cached_ai"
        latest = profile["observations"][-1]
        assert latest["land_cover_pct"][cover] > 50
        assert latest["soil_moisture_pct"] > 0 and latest["ndvi"] is not None
        assert latest["scenes"][0]["id"].startswith("COPERNICUS/S2_SR_HARMONIZED/")
        assert latest["image"].startswith("data:image/png;base64,")
        inputs = {"days": 28, "demand_mm_day": 3, "storage_capacity_mm": 100, "initial_storage_pct": 50}

        def run(rain):
            response = api.post(f"/api/land/analyses/{identifier}/scenario", json={**inputs, "rain_mm_week": rain})
            assert response.status_code == 200, response.text
            return response.json()["frames"]

        drought, storm = run(2), run(85)
        assert [frame["day"] for frame in drought] == [0, 7, 14, 21, 28]
        assert drought[0]["mean_storage_pct"] == storm[0]["mean_storage_pct"] == 50
        assert drought[-1]["mean_storage_pct"] < drought[0]["mean_storage_pct"] < storm[-1]["mean_storage_pct"]
        assert drought[-1]["image"] != storm[-1]["image"]
        terrain = api.get(f"/api/land/analyses/{identifier}/terrain").json()["elevations_m"]
        first_grid = drought[0]["terrain_storage_pct"]
        assert [len(row) for row in first_grid] == [len(row) for row in terrain]
        assert {sample for row in first_grid for sample in row} == {None, 50}
        assert drought[-1]["terrain_storage_pct"] != storm[-1]["terrain_storage_pct"]
        assert all((start is None) == (final is None)
                   for first, last in zip(first_grid, storm[-1]["terrain_storage_pct"], strict=True)
                   for start, final in zip(first, last, strict=True))
        report = api.get(f"/api/land/analyses/{identifier}/report.pdf")
        assert report.status_code == 200
        text = " ".join(page.extract_text() for page in PdfReader(BytesIO(report.content)).pages)
        assert profile["title"] in text
        assert "Cached AI-generated summary" in text and "NDMI" in text and cover in text
        assert api.post("/api/land/analyses", json={"aoi": profile["aoi"], "end": "2025-03-31"}).status_code == 503


def test_optional_live_summary_receives_only_derived_facts_and_rejects_digits(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LAND_LLM_API_KEY", "test-key")
    profile = read_demos(DEMO_DIRECTORY)["thar-dryland"].profile

    def response(request, timeout):
        submitted = json.loads(request.data)
        facts = json.loads(submitted["input"])
        assert {"image", "scenes", "coordinates"}.isdisjoint(facts[0])
        assert facts[0]["ndvi"] == profile.observations[0].ndvi
        return BytesIO(b'{"output":[{"type":"message","content":[{"type":"output_text","text":"A claim of 99 percent."}]}]}')

    monkeypatch.setattr(land_narrative, "urlopen", response)
    with pytest.raises(RuntimeError, match="report check"):
        land_narrative.generate_narrative(profile)


def test_groq_uses_its_own_endpoint_and_excludes_location(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("LAND_LLM_API_KEY", "test-openai-key")
    monkeypatch.delenv("LAND_GROQ_MODEL", raising=False)
    profile = read_demos(DEMO_DIRECTORY)["thar-dryland"].profile

    def response(request, timeout):
        assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-groq-key"
        body = json.loads(request.data)
        assert body["model"] == "openai/gpt-oss-20b"
        facts = json.loads(body["messages"][1]["content"])
        assert {"image", "scenes", "aoi", "image_offset"}.isdisjoint(facts[0])
        return BytesIO(b'{"choices":[{"message":{"content":"Bare ground was the leading class."}}]}')

    monkeypatch.setattr(land_narrative, "urlopen", response)
    assert land_narrative.ai_available()
    assert land_narrative.generate_narrative(profile).text == "Bare ground was the leading class."


def test_guidance_varies_by_reader_and_purpose_with_no_ai_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LAND_LLM_API_KEY", raising=False)
    with TestClient(create_app(Settings())) as api:
        path = "/api/land/analyses/punjab-farmland/guidance"
        crops = api.post(path, json={"role": "farmer", "purpose": "crops", "use_ai": True}).json()
        site = api.post(path, json={"role": "buyer", "purpose": "site"}).json()
        assert crops["ai_status"] == "unavailable" and crops["narrative"] is None
        assert "0.69" in crops["evidence"] and "crop calendar" in crops["checks"][1]
        assert "86.38%" in site["evidence"] and "ownership" in site["checks"][1]
        assert api.post(path, json={"role": "made-up", "purpose": "site"}).status_code == 422


def test_personalized_groq_prompt_includes_role_and_purpose_without_boundary(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def response(request, timeout):
        messages = json.loads(request.data)["messages"]
        assert "Land buyer" in messages[0]["content"] and "Screen a plot" in messages[0]["content"]
        assert "coordinates" not in messages[1]["content"]
        return BytesIO(b'{"choices":[{"message":{"content":"Check local drainage during your site visit."}}]}')

    monkeypatch.setattr(land_narrative, "urlopen", response)
    with TestClient(create_app(Settings())) as api:
        payload = {"role": "buyer", "purpose": "site", "use_ai": True}
        result = api.post("/api/land/analyses/thar-dryland/guidance", json=payload).json()
        assert result["ai_status"] == "ready"
        assert result["narrative"] == {"source": "ai", "text": "Check local drainage during your site visit."}


def test_land_stream_reports_provider_stages_and_stores_the_result(monkeypatch):
    bundle = read_demos(DEMO_DIRECTORY)["thar-dryland"]
    live = land_routes.replace(bundle, profile=bundle.profile.model_copy(update={"id": "stream-fixture", "terrain": None}))

    def build(project, request, max_km2, progress):
        for stage in ("sources", "pixels", "summary"):
            progress(stage)
        return live

    monkeypatch.setattr(land_routes, "build_profile", build)
    payload = {"aoi": bundle.profile.aoi.model_dump(mode="json"), "end": "2025-03-31", "months": 3}
    with TestClient(create_app(Settings(earth_engine_project="test-project"))) as api:
        response = api.post("/api/land/analyses/stream", json=payload)
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[:-1] == [{"type": "stage", "data": stage} for stage in ("sources", "pixels", "summary")]
        assert events[-1]["type"] == "result"
        assert api.get("/api/land/analyses/stream-fixture").json() == events[-1]["data"]

    with TestClient(create_app(Settings())) as api:
        result = api.post("/api/land/analyses/stream", json=payload)
        event = json.loads(result.text)
        assert event["type"] == "error" and "require Earth Engine" in event["data"]


@pytest.mark.parametrize("identifier", ["punjab-farmland", "thar-dryland"])
def test_cached_terrain_contains_real_surface_samples_with_earth_engine_disabled(identifier):
    with TestClient(create_app(Settings())) as api:
        result = api.get(f"/api/land/analyses/{identifier}/terrain")
        assert result.status_code == 200
        data = result.json()
        rows = data["elevations_m"]
        assert data["cell_m"] >= 30 and "COPERNICUS/DEM/GLO30" in data["source"]
        assert 2 <= len(rows) <= 56 and all(len(row) == len(rows[0]) <= 56 for row in rows)
        values = [sample for row in rows for sample in row if sample is not None]
        assert max(values) > min(values)
        assert api.get("/api/land/analyses/unknown/terrain").status_code == 404
