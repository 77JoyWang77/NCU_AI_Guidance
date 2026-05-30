"""Per-user daily request quota for PDF chat.

Counts requests in pdf_agent_messages rather than token observations
(which belong to the source system's Langfuse trace tables).

Atomic reservation: an in-flight counter tracks requests that have passed
the quota check but whose agent messages are not yet written.  Since this
application runs as a single Uvicorn worker (WEB_CONCURRENCY=1), the asyncio
event loop guarantees that the check-and-increment is never interleaved with
another request's check, so this is safe without extra locking.

Multi-worker NOTE: if WEB_CONCURRENCY > 1, migrate to a PostgreSQL advisory
lock or atomic UPDATE ... RETURNING counter.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.database_pdf import PdfSessionLocal
from app.models.pdf_models import PdfAgentMessage

_DEFAULT_DAILY_LIMIT = int(__import__("os").getenv("PDF_CHAT_DAILY_LIMIT", "50"))

# Process-local in-flight counters: effective_id → count of requests that
# passed the quota check but are still being processed.
_in_flight: dict[str, int] = {}


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _db_count(effective_id: str) -> int:
    """Return today's completed request count from the DB."""
    with PdfSessionLocal() as db:
        return (
            db.query(func.count(PdfAgentMessage.id))
            .filter(
                PdfAgentMessage.user_id == effective_id,
                PdfAgentMessage.created_at >= _today_start(),
            )
            .scalar() or 0
        )


def check_quota(user_id: str | None, anon_id: str | None = None) -> None:
    """Raise HTTP 429 if the effective identity has exceeded its daily quota.

    effective_id priority: user_id (authenticated) > anon_id (X-Anon-Session).
    If neither is present the request is untracked and passes through.
    """
    effective_id = user_id or anon_id
    if not effective_id:
        return

    db_count = _db_count(effective_id)
    in_flight = _in_flight.get(effective_id, 0)

    if db_count + in_flight >= _DEFAULT_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"今日 PDF 問答請求數已達上限（{_DEFAULT_DAILY_LIMIT} 次）",
        )


@contextmanager
def quota_reservation(user_id: str | None, anon_id: str | None = None):
    """Context manager that holds an in-flight slot for the duration of a request.

    Usage:
        with quota_reservation(user_id, anon_id):
            ... run LLM ...

    Automatically releases the slot on exit (success, exception, or cancel).
    """
    effective_id = user_id or anon_id
    if effective_id:
        _in_flight[effective_id] = _in_flight.get(effective_id, 0) + 1
    try:
        yield
    finally:
        if effective_id:
            count = _in_flight.get(effective_id, 1) - 1
            if count <= 0:
                _in_flight.pop(effective_id, None)
            else:
                _in_flight[effective_id] = count


def enter_reservation(user_id: str | None, anon_id: str | None = None) -> str | None:
    """Increment the in-flight counter; returns effective_id for exit_reservation()."""
    effective_id = user_id or anon_id
    if effective_id:
        _in_flight[effective_id] = _in_flight.get(effective_id, 0) + 1
    return effective_id


def exit_reservation(effective_id: str | None) -> None:
    """Decrement the in-flight counter incremented by enter_reservation()."""
    if effective_id:
        count = _in_flight.get(effective_id, 1) - 1
        if count <= 0:
            _in_flight.pop(effective_id, None)
        else:
            _in_flight[effective_id] = count
