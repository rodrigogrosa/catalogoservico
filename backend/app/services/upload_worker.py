"""Upload job worker — consumes from the Redis Stream and processes upload jobs.

Each running backend instance starts one worker thread.  The Redis Streams
consumer group guarantees that every job is processed by exactly one worker even
when multiple replicas are running, and that jobs survive a process restart
(pending entries are reclaimed via XAUTOCLAIM on startup).

Job types
---------
  "upload"     — files are already saved to disk; worker calls
                 project_service.create_project_from_saved_files()
  "import_url" — worker downloads the URL then calls
                 create_project_from_saved_files()

Status lifecycle
----------------
  queued → processing → done
                     ↘ failed
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services import upload_queue as uq

logger = logging.getLogger(__name__)

_CONSUMER_NAME = f"worker-{uuid4().hex[:8]}"
_started = False
_start_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Job processors
# ---------------------------------------------------------------------------

def _process_upload(job: dict[str, Any]) -> str:
    """Process a file-based upload job.  Returns the project_id on success."""
    from app.services.project_service import ProjectService  # lazy import

    saved_files_raw: list[str] = job.get("saved_files") or []
    saved_files = [Path(p) for p in saved_files_raw]
    layout: dict[str, Any] = job.get("layout") or {}
    project_name: str = job.get("project_name") or "projeto-3d"
    origin_url: str | None = job.get("origin_url") or None

    # Rebuild layout dict — folder values are stored as strings
    if layout.get("folders"):
        layout["folders"] = {k: Path(v) for k, v in layout["folders"].items()}

    svc = ProjectService()
    result = svc.create_project_from_saved_files(
        saved_files=saved_files,
        layout=layout,
        project_name=project_name,
        origin_url=origin_url,
    )
    return str(result.id)


def _process_import_url(job: dict[str, Any]) -> str:
    """Download the URL then process.  Returns the project_id on success."""
    from app.services.project_service import ProjectService  # lazy import
    import asyncio  # noqa: PLC0415

    url: str = job.get("url") or ""
    project_name: str = job.get("project_name") or "projeto-3d"

    svc = ProjectService()
    # create_project_from_url is async — run it in a new event loop inside the thread
    result = asyncio.run(svc.create_project_from_url(url, requested_name=project_name or None))
    return str(result.id)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _handle_message(msg_id: str, fields: dict[str, str]) -> None:
    job = uq.parse_message(fields)
    job_id: str = job.get("job_id") or msg_id
    job_type: str = job.get("type") or "upload"

    logger.info("upload_worker: processing job_id=%s type=%s", job_id, job_type)
    uq.set_job_status(job_id, "processing")

    try:
        if job_type == "import_url":
            project_id = _process_import_url(job)
        else:
            project_id = _process_upload(job)

        uq.set_job_status(job_id, "done", project_id=project_id)
        uq.ack_job(msg_id)
        logger.info("upload_worker: job done job_id=%s project_id=%s", job_id, project_id)
    except Exception as exc:
        error_msg = str(exc)[:512]
        uq.set_job_status(job_id, "failed", error=error_msg)
        uq.ack_job(msg_id)  # ack to avoid infinite re-delivery of poison messages
        logger.error("upload_worker: job failed job_id=%s error=%s", job_id, error_msg, exc_info=True)


def _worker_loop() -> None:
    logger.info("upload_worker: started consumer=%s", _CONSUMER_NAME)

    # Reclaim any stale messages left by a previously crashed worker
    try:
        stale = uq.reclaim_stale_jobs(_CONSUMER_NAME, batch=20)
        for msg_id, fields in stale:
            logger.info("upload_worker: reclaimed stale msg=%s", msg_id)
            _handle_message(msg_id, fields)
    except Exception as exc:
        logger.warning("upload_worker: stale reclaim failed: %s", exc)

    while True:
        try:
            messages = uq.read_pending_jobs(_CONSUMER_NAME, batch=3)
            for msg_id, fields in messages:
                _handle_message(msg_id, fields)
        except Exception as exc:
            logger.warning("upload_worker: read loop error: %s", exc)
            time.sleep(2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start() -> None:
    """Start the upload worker thread.  Safe to call multiple times (idempotent)."""
    global _started
    with _start_lock:
        if _started:
            return
        # Only start if Redis is reachable
        url = os.environ.get("REDIS_URL", "")
        if not url:
            logger.info("upload_worker: REDIS_URL not set — async upload queue disabled")
            return
        t = threading.Thread(target=_worker_loop, daemon=True, name="upload-worker")
        t.start()
        _started = True
        logger.info("upload_worker: background thread started")
