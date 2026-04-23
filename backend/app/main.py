from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging


settings = get_settings()
configure_logging()

app = FastAPI(
    title="SnapMaker3d Studio API",
    version="0.1.0",
    description="Backend para análise, conversão e preparação de projetos 3D para Snapmaker.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
app.mount("/storage", StaticFiles(directory=settings.storage_root, check_dir=False), name="storage")


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": "SnapMaker3d Studio API",
        "docs": "/docs",
        "storage_root": str(settings.storage_root),
    }
