from dataclasses import dataclass
from math import isfinite
from os import getenv


@dataclass(frozen=True)
class Settings:
    max_aoi_km2: float = 100.0
    earth_engine_configured: bool = False
    origins: tuple[str, ...] = ()
    earth_engine_project: str = ""
    processing_scale_m: int = 10
    stateless: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        limit = float(getenv("MAX_AOI_KM2") or "100")
        if not isfinite(limit) or limit <= 0:
            raise ValueError("MAX_AOI_KM2 must be a finite, positive number.")
        origins = tuple(
            origin.strip() for origin in getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()
        )
        project = getenv("EE_PROJECT_ID", "").strip()
        configured_provider = getenv("SAR_PROVIDER", "").strip()
        if configured_provider not in {"", "earth_engine", "cached"}:
            raise ValueError("SAR_PROVIDER must be earth_engine or cached.")
        scale = int(getenv("PROCESSING_SCALE_M") or "10")
        if not 10 <= scale <= 100:
            raise ValueError("PROCESSING_SCALE_M must be between 10 and 100 metres.")
        return cls(limit, bool(project), origins, project if configured_provider != "cached" else "", scale)
