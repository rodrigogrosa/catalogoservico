from __future__ import annotations

import asyncio
import logging
import sys
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import clear_request_id, configure_logging, get_request_id, set_request_id


settings = get_settings()
configure_logging()
logger = logging.getLogger("app.http")

app = FastAPI(
    title="SnapMaker3d Studio API",
    version="0.1.0",
    description="Backend para análise, conversão e preparação de projetos 3D para Snapmaker.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)

app.include_router(api_router, prefix="/api/v1")
app.mount("/storage", StaticFiles(directory=settings.storage_root, check_dir=False), name="storage")


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'"
    ),
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    set_request_id(request_id)
    start = perf_counter()
    logger.info(
        "request_started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "client": request.client.host if request.client else None,
            "origin": request.headers.get("origin"),
            "content_length": request.headers.get("content-length"),
            "user_agent": request.headers.get("user-agent"),
        },
    )

    response = None
    try:
        response = await call_next(request)
        return response
    except asyncio.CancelledError:
        logger.warning(
            "request_cancelled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "content_length": request.headers.get("content-length"),
            },
        )
        raise
    finally:
        duration_ms = round((perf_counter() - start) * 1000, 2)
        if response is not None:
            response.headers["x-request-id"] = request_id
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": getattr(response, "status_code", 500),
                "duration_ms": duration_ms,
                "content_length": request.headers.get("content-length"),
            },
        )
        clear_request_id()


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "request_validation_error",
        extra={
            "method": request.method,
            "path": request.url.path,
            "errors": exc.errors(),
        },
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": get_request_id()},
        headers={"x-request-id": get_request_id()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    try:
        logger.exception(
            "request_unhandled_exception",
            extra={
                "method": request.method,
                "path": request.url.path,
            },
        )
    except Exception as log_exc:  # noqa: BLE001
        print(f"LOGGER FAILED: {log_exc!r} | Original exception: {exc!r}", file=sys.stderr)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno inesperado.", "request_id": get_request_id()},
        headers={"x-request-id": get_request_id()},
    )


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": "SnapMaker3d Studio API",
        "docs": "/docs",
        "storage_root": str(settings.storage_root),
    }
