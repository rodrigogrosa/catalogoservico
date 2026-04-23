import os

import uvicorn

from app.core.config import get_settings


if __name__ == "__main__":
    settings = get_settings()
    reload_enabled = os.getenv("UVICORN_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run("app.main:app", host=settings.backend_host, port=settings.backend_port, reload=reload_enabled)
