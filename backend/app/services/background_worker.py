"""
Lightweight in-process background worker queue.

Replaces bare ``threading.Thread`` calls for fire-and-forget work:
- Bounded queue with backpressure (max 256 pending tasks).
- Fixed thread pool (default 2 workers) — won't flood NFS or the LLM.
- Per-task retry up to ``max_retries`` with exponential back-off.
- All exceptions are logged; workers never die silently.

Usage::

    from app.services.background_worker import enqueue

    enqueue("post_import_ai", run_fn, project_id="meu-projeto_v001")
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (overridable via env vars)
# ---------------------------------------------------------------------------
_WORKER_COUNT = int(os.environ.get("BG_WORKER_COUNT", "2"))
_QUEUE_MAX = int(os.environ.get("BG_QUEUE_MAX", "256"))
_MAX_RETRIES = int(os.environ.get("BG_MAX_RETRIES", "3"))
_BASE_BACKOFF = float(os.environ.get("BG_BASE_BACKOFF_SECONDS", "2.0"))

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_task_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=_QUEUE_MAX)
_workers: list[threading.Thread] = []
_started = False
_start_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _worker_loop() -> None:
    while True:
        item = _task_queue.get()
        if item is None:
            # Poison pill — orderly shutdown.
            _task_queue.task_done()
            break

        name: str = item["name"]
        fn: Callable[..., Any] = item["fn"]
        kwargs: dict[str, Any] = item["kwargs"]
        attempt: int = item["attempt"]
        max_retries: int = item["max_retries"]

        try:
            fn(**kwargs)
            logger.debug("bg_task_done", extra={"task": name, "attempt": attempt})
        except Exception as exc:  # noqa: BLE001
            if attempt < max_retries:
                backoff = _BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    "bg_task_retry",
                    extra={"task": name, "attempt": attempt, "backoff_s": backoff, "error": str(exc)},
                )
                time.sleep(backoff)
                retry_item = {**item, "attempt": attempt + 1}
                try:
                    _task_queue.put_nowait(retry_item)
                except queue.Full:
                    logger.error("bg_task_queue_full_drop_retry", extra={"task": name})
            else:
                logger.error(
                    "bg_task_failed",
                    extra={"task": name, "attempt": attempt, "error": str(exc)},
                    exc_info=True,
                )
        finally:
            _task_queue.task_done()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_workers(count: int = _WORKER_COUNT) -> None:
    """Start daemon worker threads.  Safe to call multiple times."""
    global _started
    with _start_lock:
        if _started:
            return
        for i in range(count):
            t = threading.Thread(
                target=_worker_loop,
                daemon=True,
                name=f"bg-worker-{i}",
            )
            t.start()
            _workers.append(t)
        _started = True
        logger.info("bg_workers_started", extra={"count": count})


def enqueue(
    task_name: str,
    fn: Callable[..., Any],
    *,
    max_retries: int = _MAX_RETRIES,
    **kwargs: Any,
) -> bool:
    """Submit a task to the background queue.

    Returns ``True`` if accepted, ``False`` if the queue is full (task dropped).
    Workers are auto-started on first enqueue.
    """
    start_workers()
    item: dict[str, Any] = {
        "name": task_name,
        "fn": fn,
        "kwargs": kwargs,
        "attempt": 0,
        "max_retries": max_retries,
    }
    try:
        _task_queue.put_nowait(item)
        logger.debug("bg_task_enqueued", extra={"task": task_name})
        return True
    except queue.Full:
        logger.error("bg_task_queue_full_drop", extra={"task": task_name})
        return False
