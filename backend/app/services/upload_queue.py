"""Redis Streams adapter for asynchronous upload jobs.

Design
------
* Stream key  : ``sm3d:upload_jobs``
* Consumer grp: ``sm3d_upload_workers``
* Job status  : Redis Hash  ``sm3d:job:{job_id}``
  Fields: status, project_id, error, created_at, updated_at

Delivery guarantee
------------------
  XADD  → message is durable in Redis
  XREADGROUP NOACK=False → message stays in PEL (Pending Entries List) until
  the worker calls XACK after successful processing.
  On crash/restart, XAUTOCLAIM reclaims stale pending messages.

Fallback
--------
  When REDIS_URL is not set (local dev), every public function degrades
  gracefully: enqueue returns a job_id but marks status="no_queue" so the
  caller can detect it and fall back to synchronous processing.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

STREAM_KEY = "sm3d:upload_jobs"
GROUP_NAME = "sm3d_upload_workers"
JOB_TTL_SECONDS = 3600 * 24  # 24 h — then Redis auto-expires the hash
CLAIM_IDLE_MS = 30_000        # 30 s idle before a message can be re-claimed


# ---------------------------------------------------------------------------
# Internal client
# ---------------------------------------------------------------------------

def _client():
    """Return a synchronous redis client, or None if not configured."""
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis  # type: ignore[import]
        return redis.from_url(
            url,
            socket_connect_timeout=1.0,
            socket_timeout=2.0,
            decode_responses=True,
        )
    except Exception as exc:
        logger.debug("upload_queue: redis init failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Consumer group bootstrap (idempotent)
# ---------------------------------------------------------------------------

def ensure_group(r) -> None:  # noqa: ANN001
    """Create the consumer group if it does not exist yet.  Safe to call repeatedly."""
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
    except Exception as exc:
        # BUSYGROUP = group already exists — ignore
        if "BUSYGROUP" not in str(exc):
            logger.warning("upload_queue: xgroup_create failed: %s", exc)


# ---------------------------------------------------------------------------
# Job status helpers
# ---------------------------------------------------------------------------

def _job_key(job_id: str) -> str:
    return f"sm3d:job:{job_id}"


def set_job_status(job_id: str, status: str, *, project_id: str = "", error: str = "") -> None:
    r = _client()
    if r is None:
        return
    try:
        now = datetime.now(tz=timezone.utc).isoformat()
        mapping: dict[str, str] = {
            "status": status,
            "project_id": project_id,
            "error": error,
            "updated_at": now,
        }
        key = _job_key(job_id)
        # Preserve created_at on updates
        if not r.hexists(key, "created_at"):
            mapping["created_at"] = now
        r.hset(key, mapping=mapping)
        r.expire(key, JOB_TTL_SECONDS)
    except Exception as exc:
        logger.warning("upload_queue: set_job_status failed job=%s: %s", job_id, exc)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    r = _client()
    if r is None:
        return None
    try:
        data = r.hgetall(_job_key(job_id))
        return dict(data) if data else None
    except Exception as exc:
        logger.warning("upload_queue: get_job_status failed job=%s: %s", job_id, exc)
        return None


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------

def enqueue_upload_job(job_id: str, payload: dict[str, Any]) -> bool:
    """Publish a job message to the Redis Stream.

    ``payload`` must be JSON-serialisable. All values are stored as strings.
    Returns True if enqueued successfully, False if Redis is unavailable
    (caller should fall back to synchronous processing).
    """
    r = _client()
    if r is None:
        logger.info("upload_queue: Redis unavailable — job %s will run synchronously", job_id)
        return False
    try:
        ensure_group(r)
        fields = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in payload.items()}
        fields["job_id"] = job_id
        r.xadd(STREAM_KEY, fields, maxlen=5_000, approximate=True)
        set_job_status(job_id, "queued")
        logger.info("upload_queue: job enqueued job_id=%s type=%s", job_id, payload.get("type"))
        return True
    except Exception as exc:
        logger.error("upload_queue: enqueue failed job=%s: %s", job_id, exc)
        return False


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------

def read_pending_jobs(consumer_name: str, batch: int = 5) -> list[tuple[str, dict[str, str]]]:
    """Read up to ``batch`` unacked messages for this consumer.

    Returns a list of (message_id, fields) tuples.
    """
    r = _client()
    if r is None:
        return []
    try:
        ensure_group(r)
        result = r.xreadgroup(
            GROUP_NAME,
            consumer_name,
            {STREAM_KEY: ">"},
            count=batch,
            block=2000,  # ms — long-poll, avoids busy loop
        )
        if not result:
            return []
        messages: list[tuple[str, dict[str, str]]] = []
        for _stream, entries in result:
            for msg_id, fields in entries:
                messages.append((msg_id, fields))
        return messages
    except Exception as exc:
        logger.warning("upload_queue: read_pending_jobs failed: %s", exc)
        return []


def ack_job(msg_id: str) -> None:
    """Acknowledge successful processing."""
    r = _client()
    if r is None:
        return
    try:
        r.xack(STREAM_KEY, GROUP_NAME, msg_id)
    except Exception as exc:
        logger.warning("upload_queue: xack failed msg=%s: %s", msg_id, exc)


def reclaim_stale_jobs(consumer_name: str, batch: int = 5) -> list[tuple[str, dict[str, str]]]:
    """Re-claim messages idle for >CLAIM_IDLE_MS from *any* consumer.

    Call this at worker startup to recover jobs left behind by a crashed worker.
    """
    r = _client()
    if r is None:
        return []
    try:
        result = r.xautoclaim(
            STREAM_KEY,
            GROUP_NAME,
            consumer_name,
            min_idle_time=CLAIM_IDLE_MS,
            start_id="0-0",
            count=batch,
        )
        # xautoclaim returns (next_start_id, [(msg_id, fields), ...], deleted_ids)
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        return [(mid, fields) for mid, fields in entries]
    except Exception as exc:
        logger.debug("upload_queue: xautoclaim failed (may be unsupported Redis version): %s", exc)
        return []


# ---------------------------------------------------------------------------
# Parse message
# ---------------------------------------------------------------------------

def parse_message(fields: dict[str, str]) -> dict[str, Any]:
    """Decode a Redis Stream message back into a Python dict."""
    out: dict[str, Any] = {}
    for k, v in fields.items():
        try:
            out[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            out[k] = v
    return out
