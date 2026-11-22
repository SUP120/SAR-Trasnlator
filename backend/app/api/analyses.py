from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Response

from ..analysis import METHOD_VERSION, AnalysisRequest, LiveRequest, SyntheticRequest, run_analysis
from ..aoi import InvalidAoi, validate_aoi
from ..cached_events import EventCatalog
from ..config import Settings
from ..explanations import Explanation, Language, explain
from ..jobs import Jobs, QueueFull, Snapshot
from ..pipeline.raster import GridError, LayerName, Parameters, RenderedLayers
from ..providers.earth_engine import EarthEngineProvider
from ..providers.synthetic import EXAMPLE_SLUG, EXAMPLE_TITLE, SyntheticProvider
from ..reports.pdf import build_report

JobId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


def analysis_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api")
    jobs = Jobs()
    catalog = EventCatalog()
    example = SyntheticProvider()
    earth = EarthEngineProvider(settings.earth_engine_project) if settings.earth_engine_project else None
    defaults = Parameters()
    practice_id = sha256(f"{EXAMPLE_SLUG}:{METHOD_VERSION}".encode()).hexdigest()[:32]

    @lru_cache(maxsize=1)
    def practice_result() -> tuple[Snapshot, RenderedLayers]:
        try:
            outcome = run_analysis(practice_id, SyntheticRequest(source="synthetic"), example, defaults,
                                   settings.max_aoi_km2, lambda _: None)
        except (GridError, InvalidAoi) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if outcome.result is None or outcome.layers is None:
            raise HTTPException(status_code=503, detail="The synthetic example is unavailable.")
        return Snapshot(id=practice_id, source="synthetic", status="done", result=outcome.result), outcome.layers

    def get_job(job_id: str):
        cached = catalog.by_id.get(job_id)
        if cached is not None:
            return cached.snapshot, cached.layers
        if settings.stateless and job_id == practice_id:
            return practice_result()
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="This analysis has expired or does not exist.")
        return job

    def get_result(job_id: str):
        snapshot, layers = get_job(job_id)
        if snapshot.result is None or layers is None:
            raise HTTPException(status_code=409, detail="The analysis has no result available.")
        return snapshot.result, layers

    @router.get("/demo/events")
    def list_examples() -> list[dict[str, str]]:
        return [
            {"slug": EXAMPLE_SLUG, "title": EXAMPLE_TITLE, "source": "synthetic"},
            *({"slug": event.slug, "title": event.title, "source": "cached"} for event in catalog.by_slug.values()),
        ]

    @router.get("/demo/events/{slug}", response_model=Snapshot)
    def historical_event(slug: str) -> Snapshot:
        event = catalog.by_slug.get(slug)
        if event is None:
            raise HTTPException(status_code=404, detail="This historical example is unavailable.")
        return event.snapshot

    @router.post("/analyses", response_model=Snapshot, status_code=202)
    def submit(analysis: AnalysisRequest, background: BackgroundTasks):
        provider = example
        params = defaults
        if isinstance(analysis, LiveRequest):
            if earth is None:
                raise HTTPException(status_code=503, detail="Live analysis requires a registered Earth Engine project.")
            try:
                validate_aoi(analysis.aoi, settings.max_aoi_km2)
            except InvalidAoi as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            provider = earth
            params = replace(defaults, scale_m=settings.processing_scale_m)
        elif settings.stateless:
            return practice_result()[0]
        try:
            job = jobs.create(analysis.source)
        except QueueFull as error:
            raise HTTPException(status_code=429, detail=str(error), headers={"Retry-After": "5"}) from error
        background.add_task(jobs.run, job.id, analysis, provider, params, settings.max_aoi_km2)
        return job

    @router.get("/analyses/{job_id}", response_model=Snapshot)
    def status(job_id: JobId, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return get_job(job_id)[0]

    @router.get("/analyses/{job_id}/layers/{layer}.png")
    def layer_image(job_id: JobId, layer: LayerName):
        _, layers = get_result(job_id)
        return Response(layers.pngs[layer], media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

    @router.post("/analyses/{job_id}/explain", response_model=Explanation)
    def explanation(job_id: JobId, lang: Language = "en"):
        result, _ = get_result(job_id)
        return explain(result, lang)

    @router.get("/analyses/{job_id}/report.pdf")
    def report(job_id: JobId, lang: Language = "en"):
        result, layers = get_result(job_id)
        label = result.cached_event.slug if result.cached_event else f"{result.source}-{job_id[:8]}"
        filename = f"sar-translator-{label}-{lang}.pdf"
        return Response(build_report(result, layers, lang), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"})

    return router
