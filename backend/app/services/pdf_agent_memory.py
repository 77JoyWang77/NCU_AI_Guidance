"""Unified memory abstraction for PDF chat agents.

Read and write policies are declared here; implementation lives in pdf_memory_service.py
and pdf_user_profile_service.py.
The router uses this module to inject memory context and record outcomes.

Policy rules:
- Only research writes to long-term memory (store), context_summary, and user_profile.
- Retrieval/chat can read context_summary for follow-up disambiguation.
- Long-term memory (semantic search) is enabled for research and chat only.
- User profile is read by research and chat; written only by research (background).
- retrieval memory is framing context only, never citation evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.pdf.types import AgentResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryRead:
    context_summary: bool = True
    long_term: bool = False
    user_profile: bool = False


@dataclass(frozen=True)
class MemoryWrite:
    context_summary: bool = False
    long_term: bool = False
    user_profile: bool = False


MEMORY_READ_POLICY: dict[str, MemoryRead] = {
    "research":  MemoryRead(context_summary=True,  long_term=True,  user_profile=True),
    "retrieval": MemoryRead(context_summary=True,  long_term=False, user_profile=False),
    "chat":      MemoryRead(context_summary=True,  long_term=True,  user_profile=True),
}

MEMORY_WRITE_POLICY: dict[str, MemoryWrite] = {
    "research":  MemoryWrite(context_summary=True,  long_term=True,  user_profile=True),
    "retrieval": MemoryWrite(context_summary=False, long_term=False, user_profile=False),
    "chat":      MemoryWrite(context_summary=False, long_term=False, user_profile=False),
}

_CONTEXT_LABELS = {
    "context_summary": "【對話摘要】以下是本次對話的研究摘要，作為追問背景，不可作為 citation：\n",
    "long_term":       "【歷史研究記憶】以下是過去相關研究的摘要，僅供參考：\n",
    "user_profile":    "【使用者背景】以下是關於使用者的背景資訊，供回覆參考：\n",
}

# Per-component character budget for memory injection.
_MEMORY_CHAR_LIMITS = {
    "context_summary": 800,
    "long_term":       500,
    "user_profile":    300,
}


async def build_memory_context(
    agent_name: str,
    thread_id: str,
    user_id: str | None,
    query: str,
    document_id: int,
) -> dict[str, str | None]:
    """Return memory snippets keyed by type, per the agent_name's read policy."""
    policy = MEMORY_READ_POLICY.get(agent_name, MemoryRead())
    result: dict[str, str | None] = {}

    if policy.context_summary:
        try:
            import asyncio
            from app.services.pdf_memory_service import get_context_summary_text
            result["context_summary"] = await asyncio.to_thread(get_context_summary_text, thread_id)
        except Exception as exc:
            logger.debug("build_memory_context: context_summary failed: %s", exc)

    if policy.long_term and user_id:
        try:
            from app.services.pdf_memory_service import search_long_term_memory
            items = await search_long_term_memory(user_id, query, document_id=document_id)
            result["long_term"] = "\n".join(items) if items else None
        except Exception as exc:
            logger.debug("build_memory_context: long_term failed: %s", exc)

    if policy.user_profile and user_id:
        try:
            from app.services.pdf_user_profile_service import (
                get_user_profile,
                format_profile_for_injection,
            )
            profile = await get_user_profile(user_id)
            result["user_profile"] = format_profile_for_injection(profile)
        except Exception as exc:
            logger.debug("build_memory_context: user_profile failed: %s", exc)

    return {k: v for k, v in result.items() if v}


def format_memory_system_messages(memory: dict[str, str | None]) -> list[str]:
    """Format memory dict into system message strings for agent injection."""
    messages = []
    for key in ("context_summary", "long_term", "user_profile"):
        text = memory.get(key)
        if not text:
            continue
        limit = _MEMORY_CHAR_LIMITS.get(key)
        if limit and len(text) > limit:
            text = text[:limit] + "…"
        messages.append(_CONTEXT_LABELS.get(key, "") + text)
    return messages


async def record_agent_memory(
    agent_name: str,
    thread_id: str,
    user_id: str | None,
    question: str,
    result: AgentResult,
    document_id: int,
) -> None:
    """Write memory after an agent completes, per the agent_name's write policy.

    This function is always called from within a _fire_and_forget background task
    in router_agent.py, so all awaits here are already non-blocking to the response stream.
    """
    policy = MEMORY_WRITE_POLICY.get(agent_name, MemoryWrite())

    if policy.context_summary:
        try:
            from app.services.pdf_memory_service import update_context_summary
            await update_context_summary(thread_id, question, result)
        except Exception as exc:
            logger.warning("record_agent_memory: context_summary write failed: %s", exc)

    if policy.long_term and user_id:
        try:
            from app.services.pdf_memory_service import store_long_term_memory
            await store_long_term_memory(user_id, thread_id, document_id, question, result)
        except Exception as exc:
            logger.warning("record_agent_memory: long_term write failed: %s", exc)

    if policy.user_profile and user_id:
        try:
            from app.services.pdf_user_profile_service import update_user_profile
            await update_user_profile(user_id, question, result.response)
        except Exception as exc:
            logger.warning("record_agent_memory: user_profile write failed: %s", exc)
