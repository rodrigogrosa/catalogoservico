"""API routes for the Super Reviewer Agent and QA Suite Agent.

/system/review:
  GET    /        — latest review report
  POST   /run     — trigger review now (background task or sync)

/system/qa-suite:
  GET    /        — latest QA suite result
  POST   /run     — run all test layers (sync, returns full report)
  GET    /stream  — SSE stream of a running suite
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.auth import require_current_user, require_current_user_or_query_token
from app.schemas.auth import AuthUser
from app.services.reviewer_service import ReviewerService
from app.services.qa_suite_service import QASuiteService, get_current_run, get_run_lines

router = APIRouter()

# Singleton service instances (lightweight, no heavy init)
_reviewer = ReviewerService()
_qa_suite = QASuiteService()


# ── Review endpoints ─────────────────────────────────────────────────────────

@router.get("/review")
def get_review_report(current_user: AuthUser = Depends(require_current_user)) -> dict[str, Any]:
    """Return the most recent review report."""
    return _reviewer.get_report()


@router.post("/review/run")
def run_review(
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(require_current_user),
) -> dict[str, Any]:
    """
    Trigger a full system review.
    Runs in background and returns immediately with a status message.
    """
    background_tasks.add_task(_reviewer.run_review)
    return {"status": "started", "message": "Revisão iniciada em background. Consulte GET /system/review em 30–60 segundos."}


@router.post("/review/run-sync")
def run_review_sync(current_user: AuthUser = Depends(require_current_user)) -> dict[str, Any]:
    """
    Trigger a review and wait for it to complete (may take 10–60 seconds).
    Use run (background) for production; run-sync is for debugging.
    """
    return _reviewer.run_review()


# ── QA Suite endpoints ───────────────────────────────────────────────────────

@router.get("/qa-suite")
def get_qa_suite_result(current_user: AuthUser = Depends(require_current_user)) -> dict[str, Any]:
    """Return the most recent QA suite run result."""
    return _qa_suite.get_last_result()


@router.post("/qa-suite/run")
def run_qa_suite(
    background_tasks: BackgroundTasks,
    layers: list[str] | None = Query(default=None, description="Subset: pytest, smoke, tsc, infra"),
    current_user: AuthUser = Depends(require_current_user),
) -> dict[str, Any]:
    """
    Start a QA suite run in background and return immediately.
    Poll GET /system/qa-suite or stream GET /system/qa-suite/stream for results.
    """
    background_tasks.add_task(_qa_suite.run_suite, layers)
    return {"status": "started", "message": "QA Suite iniciada. Use GET /system/qa-suite/stream para acompanhar."}


@router.post("/qa-suite/run-sync")
def run_qa_suite_sync(
    layers: list[str] | None = Query(default=None, description="Subset: pytest, smoke, tsc, infra"),
    current_user: AuthUser = Depends(require_current_user),
) -> dict[str, Any]:
    """
    Run the QA suite and wait for completion (synchronous, may take ~5 min).
    Use for debugging or CI integration.
    """
    return _qa_suite.run_suite(layers)


@router.get("/qa-suite/stream")
async def stream_qa_suite(
    token: str | None = Query(default=None, alias="token"),
    current_user: AuthUser = Depends(require_current_user_or_query_token),
) -> StreamingResponse:
    """
    SSE stream of the currently running QA suite.
    If no suite is running, emits current status and closes.
    """

    async def generate() -> Any:
        run_state = get_current_run()
        if run_state.get("status") not in ("running", None):
            # Not running — emit last result and close
            result = _qa_suite.get_last_result()
            yield f"data: {json.dumps({'type': 'done', 'result': result})}\n\n"
            return

        last_index = 0
        for _ in range(1200):  # max 10 min (1200 × 0.5s)
            state = get_current_run()
            lines = get_run_lines()
            new_lines = lines[last_index:]
            for line in new_lines:
                yield f"data: {json.dumps({'type': 'output', 'line': line})}\n\n"
            last_index = len(lines)

            if state.get("status") == "done":
                yield f"data: {json.dumps({'type': 'done', 'result': state})}\n\n"
                break

            yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
