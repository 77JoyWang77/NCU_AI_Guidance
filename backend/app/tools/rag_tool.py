"""LangChain @tool adapters for document search and retrieval.

Business logic lives in app.tools.search_core. This module is the thin adapter
layer that wraps core functions as LangChain tools and exposes the TOOLS list
consumed by runner.py.
"""
import hashlib
import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.rag import _to_page_num, _is_cover_page, _is_references_page, _is_table_or_formula_heavy
from app.tools.search_core import (
    AgentContext,
    SearchInput,
    _MAX_SEARCHES,
    run_search_report,
    set_query_expander_llm,
)

_SECTION_ALIASES: dict[str, list[str]] = {
    "abstract":      ["abstract", "摘要", "概要"],
    "introduction":  ["introduction", "緒論", "引言", "前言", "研究背景", "background"],
    "related_work":  ["related_work", "文獻回顧", "相關研究", "文獻探討", "related work"],
    "methods":       ["methods", "method", "研究方法", "實驗方法", "methodology", "方法"],
    "results":       ["results", "result", "研究成果", "實驗結果", "findings", "成果", "研究結果"],
    "conclusion":    ["conclusion", "結論", "討論", "summary", "未來工作"],
}


def _resolve_section(raw: str) -> str:
    lower = raw.lower().strip()
    for canonical, aliases in _SECTION_ALIASES.items():
        if lower in [a.lower() for a in aliases]:
            return canonical
        if any(lower in a.lower() or a.lower() in lower for a in aliases):
            return canonical
    return lower


async def _section_filtered_search(ctx: AgentContext, section_terms: list[str]) -> str | None:
    """Try Qdrant section-metadata filter for each term. Returns JSON if results found, else None."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.rag import get_vectorstore, get_dense_vectorstore, aget_document_language, RETRIEVAL_K

    if ctx.document_id is None:
        raise ValueError("document_id is required for PDF section search")

    if ctx._cached_lang is not None:
        lang = ctx._cached_lang
    else:
        lang = await aget_document_language(ctx.document_id)
        ctx._cached_lang = lang
    vs = get_dense_vectorstore() if lang == "en" else get_vectorstore()

    for term in section_terms:
        canonical = _resolve_section(term)
        must: list = []
        must.append(FieldCondition(
            key="metadata.document_id",
            match=MatchValue(value=str(ctx.document_id)),
        ))
        must.append(FieldCondition(key="metadata.section", match=MatchValue(value=canonical)))

        hits = await vs.asimilarity_search(term, k=RETRIEVAL_K, filter=Filter(must=must))
        if hits:
            chunks = []
            heavy_chunks = []
            for doc in hits[:4]:
                text = doc.page_content[:900]
                # Hard quality exclusions (same as main search path)
                if _is_cover_page(text) or _is_references_page(text):
                    continue
                # Skip already-seen chunks (#7)
                content_hash = hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()
                if content_hash in ctx.seen_chunks:
                    continue
                raw_page = doc.metadata.get("page")
                raw_page_end = doc.metadata.get("page_end", raw_page)
                p = _to_page_num(raw_page, "?")
                pe = _to_page_num(raw_page_end, p)
                src = f"p.{p}-{pe}" if pe != p else f"p.{p}"
                entry = {
                    "filename": doc.metadata.get("filename", ""),
                    "page": p,
                    "page_end": pe,
                    "section": doc.metadata.get("section", ""),
                    "content": text,
                }
                if _is_table_or_formula_heavy(text):
                    heavy_chunks.append((src, content_hash, entry))
                else:
                    chunks.append((src, content_hash, entry))
            # Append heavy chunks only when normal chunks are insufficient
            all_chunks = chunks + (heavy_chunks if len(chunks) < 2 else [])
            if all_chunks:
                for src, h, entry in all_chunks:
                    if src not in ctx.tool_sources:
                        ctx.tool_sources.append(src)
                    ctx.seen_chunks.add(h)
                return json.dumps({"results": [e for _, _, e in all_chunks]}, ensure_ascii=False)
    return None


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool(args_schema=SearchInput)
async def search_report(
    query: str,
    runtime: ToolRuntime[AgentContext],
    sub_queries: list[str] | None = None,
    display_intent: str = "",
    keyword_query: str = "",
    semantic_query: str = "",
    section_terms: list[str] | None = None,
    use_hyde: bool = False,
) -> str:
    """
    Search the current PDF for evidence about ONE focused topic.

    Use for document-specific questions about motivation, methods, experiments,
    results, limitations, definitions, sections, architectures, and frameworks.
    When asking about a specific chapter or section (e.g. '研究方法', 'conclusion',
    '結論', '緒論'), populate section_terms — section-level filtering is applied
    automatically before falling back to semantic search.
    """
    ctx = runtime.context

    max_searches = ctx.max_searches or _MAX_SEARCHES
    if ctx.search_count >= max_searches:
        return json.dumps(
            {"results": [], "HARD_STOP": f"Search limit reached ({max_searches}). Use collected evidence to answer."},
            ensure_ascii=False,
        )

    if section_terms:
        section_result = await _section_filtered_search(ctx, section_terms)
        if section_result:
            # Count against max_searches and reset consecutive_empty so the
            # model can't bypass limits by using section_terms exclusively.
            ctx.search_count += 1
            ctx.consecutive_empty = 0
            try:
                for _c in json.loads(section_result).get("results", []):
                    _h = hashlib.md5(
                        _c.get("content", "").encode("utf-8", errors="replace")
                    ).hexdigest()
                    ctx.seen_chunks.add(_h)
            except Exception:
                pass
            return section_result

    return await run_search_report(
        query=query,
        ctx=ctx,
        sub_queries=sub_queries,
        display_intent=display_intent,
        keyword_query=keyword_query,
        semantic_query=semantic_query,
        section_terms=section_terms,
        use_hyde=use_hyde,
    )


TOOLS = [search_report]

__all__ = [
    "AgentContext",
    "SearchInput",
    "TOOLS",
    "run_search_report",
    "search_report",
    "set_query_expander_llm",
]
