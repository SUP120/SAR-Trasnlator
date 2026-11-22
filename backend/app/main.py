from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .api.analyses import analysis_router
from .api.land import land_router
from .aoi import AoiPolygon, InvalidAoi, ValidatedAoi, validate_aoi
from .config import Settings


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    max_aoi_km2: float
    earth_engine: Literal["not_configured", "unverified"]
    analysis_available: bool = False


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_environment()
    api = FastAPI(title="SAR Translator", version="0.1.0")
    api.state.settings = config
    if config.origins:
        api.add_middleware(
            CORSMiddleware,
            allow_origins=config.origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @api.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        details = [{key: issue[key] for key in ("loc", "msg", "type")} for issue in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @api.get("/api/health")
    def health(current: Annotated[Settings, Depends(get_settings)]) -> Health:
        return Health(
            max_aoi_km2=current.max_aoi_km2,
            earth_engine="unverified" if current.earth_engine_configured or current.earth_engine_project else "not_configured",
            analysis_available=bool(current.earth_engine_project),
        )

    @api.post("/api/aois/validate")
    def check_area(
        geometry: AoiPolygon, current: Annotated[Settings, Depends(get_settings)],
    ) -> ValidatedAoi:
        try:
            return validate_aoi(geometry, current.max_aoi_km2)
        except InvalidAoi as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    api.include_router(analysis_router(config))
    api.include_router(land_router(config))
    return api


app = create_app()
