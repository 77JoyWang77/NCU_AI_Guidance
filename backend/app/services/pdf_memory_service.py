"""Conversation memory service for PDF chat.

Short-term:  context_summary column in pdf_conversations table.
             Research coverage results stored directly from AgentResult.coverage_result.
             answer_snippet stores the first 200 chars of the agent's response for follow-up context.
             Injected into chat/research agent calls as background context.

Long-term:   LangGraph AsyncPostgresStore (pgvector).
             Each research finding is embedded and stored with user_id/thread_id.
             Semantically similar past findings are retrieved for new questions.
             Dedup: skip storing if a very similar question already exists (score >= 0.92).
             Doc-aware sort: same-document results ranked before cross-document results.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.pdf.types import AgentResult

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "pdf_research_memories"
VECTOR_SIZE = 3072
MAX_FINDINGS = 5
LONG_TERM_LIMIT = 4
_DEDUP_THRESHOLD = 0.92


# ── Qdrant memory collection init ─────────────────────────────────────────────

def ensure_memory_collection() -> None:
    """Create pdf_research_memories Qdrant collection if it doesn't exist."""
    try:
        from app.rag import get_qdrant_client
        from qdrant_client.models import Distance, VectorParams
        client = get_qdrant_client()
        if not client.collection_exists(MEMORY_COLLECTION):
            client.create_collection(
                collection_name=MEMORY_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", MEMORY_COLLECTION)
    except Exception as exc:
        logger.warning("ensure_memory_collection failed (non-fatal): %s", exc)


# ── Short-term: context_summary ───────────────────────────────────────────────

def _load_summary(thread_id: str) -> dict:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfConversation
    try:
        with PdfSessionLocal() as db:
            row = db.query(PdfConversation.context_summary).filter(
                PdfConversation.thread_id == thread_id
            ).first()
            if row and row[0]:
                return json.loads(row[0])
    except Exception as exc:
        logger.debug("_load_summary(%s) failed: %s", thread_id, exc)
    return {"version": 2, "findings": [], "user_focus": ""}


def _save_summary(thread_id: str, data: dict) -> None:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfConversation
    try:
        with PdfSessionLocal() as db:
            conv = db.query(PdfConversation).filter(PdfConversation.thread_id == thread_id).first()
            if conv:
                conv.context_summary = json.dumps(data, ensure_ascii=False)
                db.commit()
    except Exception as exc:
        logger.warning("_save_summary failed: %s", exc)


_STATUS_LABEL = {"FILLED": "✓", "PARTIAL": "△", "EXHAUSTED": "—", "NOT_FILLED": "?"}


async def update_context_summary(
    thread_id: str,
    question: str,
    result: AgentResult,
) -> None:
    """Update context_summary directly from structured coverage_result."""
    coverage = result.coverage_result
    if not coverage:
        return

    existing = _load_summary(thread_id)
    findings = list(existing.get("findings", []))

    new_finding = {
        "question": question[:200],
        "answer_snippet": result.response[:200],
        "coverage": {
            slot_id: {
                "status": slot_data["status"],
                "label": slot_data.get("label", slot_id),
                "notes": [n[:150] for n in (slot_data.get("notes") or [])[:2]],
            }
            for slot_id, slot_data in coverage.items()
            if slot_data.get("status") in ("FILLED", "PARTIAL", "EXHAUSTED")
        },
        "sources": list(result.sources)[:5],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if not new_finding["coverage"]:
        return

    findings = [f for f in findings if f.get("question", "")[:100] != question[:100]]
    findings = findings[-(MAX_FINDINGS - 1):]
    findings.append(new_finding)

    _save_summary(thread_id, {
        "version": 2,
        "user_focus": question[:60],
        "findings": findings,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })


def get_context_summary_text(thread_id: str) -> str | None:
    """Format context_summary as structured prose for injection into _build_messages."""
    try:
        data = _load_summary(thread_id)
        findings = data.get("findings", [])
        if not findings:
            return None

        version = data.get("version", 1)

        if version >= 2:
            lines: list[str] = []
            for finding in findings[-MAX_FINDINGS:]:
                q = (finding.get("question") or "").strip()
                if q:
                    lines.append(f"問題：{q[:120]}")
                snippet = (finding.get("answer_snippet") or "").strip()
                if snippet:
                    lines.append(f"  摘要：{snippet[:150]}")
                for slot_id, slot_data in (finding.get("coverage") or {}).items():
                    status = slot_data.get("status", "")
                    label = slot_data.get("label", slot_id)
                    notes = slot_data.get("notes") or []
                    marker = _STATUS_LABEL.get(status, "?")
                    note_text = notes[0][:100] if notes else f"（{status.lower()}）"
                    lines.append(f"  {marker} {label}：{note_text}")
                srcs = "、".join((finding.get("sources") or [])[:3])
                if srcs:
                    lines.append(f"  來源：{srcs}")
            if data.get("user_focus"):
                lines.append(f"用戶關注：{data['user_focus'][:60]}")
            return "\n".join(lines) if lines else None

        # v1 fallback
        lines_v1: list[str] = []
        for f in findings[-MAX_FINDINGS:]:
            summary = (f.get("summary") or "").strip()
            if summary:
                sources = "、".join(f.get("sources", [])[:2])
                lines_v1.append(f"- {summary}" + (f"（{sources}）" if sources else ""))
        if data.get("user_focus"):
            lines_v1.append(f"用戶關注：{data['user_focus']}")
        return "\n".join(lines_v1) if lines_v1 else None
    except Exception:
        return None


# ── Long-term: LangGraph Store (AsyncPostgresStore + pgvector) ────────────────

async def store_long_term_memory(
    user_id: str,
    thread_id: str,
    document_ids: list[int] | None,
    question: str,
    result: AgentResult,
) -> None:
    """Store a research finding in LangGraph Store for semantic retrieval.

    Skips storing if a near-duplicate already exists (cosine similarity >= _DEDUP_THRESHOLD).
    """
    if not user_id:
        return
    try:
        from app.agents.pdf.runner import get_store
        store = get_store()
        if store is None:
            return
        namespace = (user_id, "research_memories")

        # Dedup: skip if very similar question already stored
        try:
            existing = await store.asearch(namespace, query=question, limit=1)
            if existing and getattr(existing[0], "score", None) is not None:
                if existing[0].score >= _DEDUP_THRESHOLD:
                    logger.debug(
                        "store_long_term_memory: skipping dedup (score=%.3f >= %.2f)",
                        existing[0].score, _DEDUP_THRESHOLD,
                    )
                    return
        except Exception as exc:
            logger.debug("store_long_term_memory: dedup check failed (non-fatal): %s", exc)

        await store.aput(namespace, str(uuid.uuid4()), {
            "question": question[:300],
            "summary": result.response[:1000],
            "sources": result.sources[:5],
            "document_ids": document_ids or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.warning("store_long_term_memory failed: %s", exc)


async def search_long_term_memory(
    user_id: str,
    query: str,
    limit: int = LONG_TERM_LIMIT,
    document_ids: list[int] | None = None,
) -> list[str]:
    """Return relevant past research findings via semantic search in LangGraph Store.

    Same-document results are ranked before cross-document results within the returned set.
    """
    if not user_id:
        return []
    try:
        from app.agents.pdf.runner import get_store
        store = get_store()
        if store is None:
            return []
        namespace = (user_id, "research_memories")
        # Fetch more than needed so we can re-rank by document overlap
        candidates = await store.asearch(namespace, query=query, limit=limit * 2)

        doc_set = set(document_ids or [])
        if doc_set:
            # Sort: same-document items first, then by original score order
            same_doc = [r for r in candidates if set(r.value.get("document_ids") or []) & doc_set]
            other_doc = [r for r in candidates if r not in same_doc]
            ranked = (same_doc + other_doc)[:limit]
        else:
            ranked = candidates[:limit]

        return [
            f"（過去研究）{r.value.get('question', '')}：{r.value.get('summary', '')[:200]}"
            for r in ranked
            if r.value.get("summary")
        ]
    except Exception as exc:
        logger.warning("search_long_term_memory failed: %s", exc)
        return []


# Aliases
async def store_research_memory(
    user_id: str,
    thread_id: str,
    document_ids: list[int] | None,
    question: str,
    result: AgentResult,
) -> None:
    await store_long_term_memory(user_id, thread_id, document_ids, question, result)


async def search_research_memories(user_id: str, query: str, limit: int = LONG_TERM_LIMIT) -> list[str]:
    return await search_long_term_memory(user_id, query, limit)
