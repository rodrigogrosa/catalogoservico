"""Shared Redis cache module.

Used by:
  - svc_projects_read   (reads with NFS fallback on miss)
  - storage_service     (invalidation on every mutation)

Design principles
-----------------
* Optional: if REDIS_URL is not set (dev / test), every function is a no-op
  and the system falls back to the in-process TTL caches in storage_service.
* Fail-silently: a Redis timeout or connection error is logged at DEBUG level
  and the caller continues as if Redis returned a miss.
* Keys are namespaced by storage root so different environments (dev / staging)
  sharing the same Redis instance never collide.

Cache structure
---------------
  sm3d:detail:{root}:{project_id}          → JSON blob, TTL 5 s
  sm3d:list:gen:{root}                     → integer counter; INCR on any write
  sm3d:list:{root}:{gen}:{page}:...        → JSON blob, TTL 15 s
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_DETAIL: int = 5    # seconds
CACHE_TTL_LIST: int = 15     # seconds

# ---------------------------------------------------------------------------
# Lazy synchronous client (used by the writer / storage_service).
# Created once per process.
# ---------------------------------------------------------------------------
_redis_sync = None


def _sync_client():
    global _redis_sync
    if _redis_sync is not None:
        return _redis_sync
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        _redis_sync = redis.from_url(
            url,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
            decode_responses=True,
        )
        return _redis_sync
    except Exception as exc:
        logger.debug("redis_sync_init_failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Lazy asynchronous client (used by the reader microservice).
# ---------------------------------------------------------------------------
_redis_async = None


async def _async_client():
    global _redis_async
    if _redis_async is not None:
        return _redis_async
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_async = aioredis.from_url(
            url,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
            decode_responses=True,
        )
        return _redis_async
    except Exception as exc:
        logger.debug("redis_async_init_failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def _detail_key(root: str, project_id: str) -> str:
    return f"sm3d:detail:{root}:{project_id}"


def _list_gen_key(root: str) -> str:
    return f"sm3d:list:gen:{root}"


def _list_key(root: str, gen: int, page: int, per_page: int, status: str | None, search: str | None) -> str:
    return f"sm3d:list:{root}:{gen}:{page}:{per_page}:{status or ''}:{search or ''}"


# ---------------------------------------------------------------------------
# Synchronous API (writer / storage_service)
# ---------------------------------------------------------------------------

def invalidate_project(root: str, project_id: str) -> None:
    """Delete the detail key and bump the list generation counter."""
    r = _sync_client()
    if r is None:
        return
    try:
        pipe = r.pipeline(transaction=False)
        pipe.delete(_detail_key(root, project_id))
        pipe.incr(_list_gen_key(root))
        pipe.execute()
    except Exception as exc:
        logger.debug("redis_invalidate_failed root=%s id=%s: %s", root, project_id, exc)


def set_project_sync(root: str, project_id: str, data: dict[str, Any]) -> None:
    r = _sync_client()
    if r is None:
        return
    try:
        r.setex(_detail_key(root, project_id), CACHE_TTL_DETAIL, json.dumps(data, default=str))
    except Exception as exc:
        logger.debug("redis_set_project_failed: %s", exc)


def get_project_sync(root: str, project_id: str) -> dict[str, Any] | None:
    r = _sync_client()
    if r is None:
        return None
    try:
        raw = r.get(_detail_key(root, project_id))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("redis_get_project_failed: %s", exc)
        return None


def get_list_gen_sync(root: str) -> int:
    r = _sync_client()
    if r is None:
        return 0
    try:
        val = r.get(_list_gen_key(root))
        return int(val) if val else 0
    except Exception:
        return 0


def set_list_sync(root: str, page: int, per_page: int, status: str | None, search: str | None,
                  data: dict[str, Any]) -> None:
    r = _sync_client()
    if r is None:
        return
    try:
        gen = get_list_gen_sync(root)
        r.setex(_list_key(root, gen, page, per_page, status, search), CACHE_TTL_LIST, json.dumps(data, default=str))
    except Exception as exc:
        logger.debug("redis_set_list_failed: %s", exc)


def get_list_sync(root: str, page: int, per_page: int, status: str | None,
                  search: str | None) -> dict[str, Any] | None:
    r = _sync_client()
    if r is None:
        return None
    try:
        gen = get_list_gen_sync(root)
        raw = r.get(_list_key(root, gen, page, per_page, status, search))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("redis_get_list_failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Asynchronous API (reader microservice)
# ---------------------------------------------------------------------------

async def get_project_async(root: str, project_id: str) -> dict[str, Any] | None:
    r = await _async_client()
    if r is None:
        return None
    try:
        raw = await r.get(_detail_key(root, project_id))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("redis_async_get_project_failed: %s", exc)
        return None


async def set_project_async(root: str, project_id: str, data: dict[str, Any]) -> None:
    r = await _async_client()
    if r is None:
        return
    try:
        await r.setex(_detail_key(root, project_id), CACHE_TTL_DETAIL, json.dumps(data, default=str))
    except Exception as exc:
        logger.debug("redis_async_set_project_failed: %s", exc)


async def get_list_gen_async(root: str) -> int:
    r = await _async_client()
    if r is None:
        return 0
    try:
        val = await r.get(_list_gen_key(root))
        return int(val) if val else 0
    except Exception:
        return 0


async def get_list_async(root: str, page: int, per_page: int, status: str | None,
                         search: str | None) -> dict[str, Any] | None:
    r = await _async_client()
    if r is None:
        return None
    try:
        gen = await get_list_gen_async(root)
        raw = await r.get(_list_key(root, gen, page, per_page, status, search))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("redis_async_get_list_failed: %s", exc)
        return None


async def set_list_async(root: str, page: int, per_page: int, status: str | None,
                         search: str | None, data: dict[str, Any]) -> None:
    r = await _async_client()
    if r is None:
        return
    try:
        gen = await get_list_gen_async(root)
        await r.setex(_list_key(root, gen, page, per_page, status, search), CACHE_TTL_LIST,
                      json.dumps(data, default=str))
    except Exception as exc:
        logger.debug("redis_async_set_list_failed: %s", exc)
