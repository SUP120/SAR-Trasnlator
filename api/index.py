from dataclasses import replace

from backend.app.config import Settings
from backend.app.main import create_app

# Vercel functions do not share the local service's in-memory job and profile stores.
app = create_app(replace(Settings.from_environment(), earth_engine_configured=False,
                         earth_engine_project="", stateless=True))
