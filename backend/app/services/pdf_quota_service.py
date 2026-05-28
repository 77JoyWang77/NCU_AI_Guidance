"""Per-user daily request quota for PDF chat.

Counts requests in pdf_agent_messages rather than token observations
(which belong to the source system's Langfuse trace tables).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.database_pdf import PdfSessionLocal
from app.models.pdf_models import PdfAgentMessage

_DEFAULT_DAILY_LIMIT = int(__import__("os").getenv("PDF_CHAT_DAILY_LIMIT", "50"))


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def check_quota(user_id: str | None) -> None:
    """Raise HTTP 429 if the user has exceeded their daily request quota.

    Anonymous users (user_id is None or empty) are not rate-limited here;
    apply IP-level throttling at the infra layer if needed.
    """
    if not user_id:
        return

    with PdfSessionLocal() as db:
        today_requests = (
            db.query(func.count(PdfAgentMessage.id))
            .filter(
                PdfAgentMessage.user_id == user_id,
                PdfAgentMessage.created_at >= _today_start(),
            )
            .scalar() or 0
        )

    if today_requests >= _DEFAULT_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"今日 PDF 問答請求數已達上限（{_DEFAULT_DAILY_LIMIT} 次）",
        )
