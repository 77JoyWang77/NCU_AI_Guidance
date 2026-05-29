"""LangChain @tool adapters for document search and retrieval.

Business logic lives in app.tools.search_core. This module is the thin adapter
layer that wraps core functions as LangChain tools and exposes the TOOLS list
consumed by runner.py.
"""
import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.tools.search_core import (
    AgentContext,
    SearchInput,
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
    from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
    from app.rag import get_vectorstore, get_dense_vectorstore, aget_document_language, RETRIEVAL_K

    lang = await aget_document_language(ctx.document_ids)
    vs = get_dense_vectorstore() if lang == "en" else get_vectorstore()

    for term in section_terms:
        canonical = _resolve_section(term)
        must: list = []
        if ctx.document_ids:
            must.append(FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in ctx.document_ids]),
            ))
        must.append(FieldCondition(key="metadata.section", match=MatchValue(value=canonical)))

        hits = await vs.asimilarity_search(term, k=RETRIEVAL_K, filter=Filter(must=must))
        if hits:
            chunks = []
            for doc in hits[:6]:
                raw_page = doc.metadata.get("page")
                raw_page_end = doc.metadata.get("page_end", raw_page)
                p = (int(raw_page) + 1) if raw_page is not None else "?"
                pe = (int(raw_page_end) + 1) if raw_page_end is not None else p
                src = f"p.{p}-{pe}" if pe != p else f"p.{p}"
                if src not in ctx.tool_sources:
                    ctx.tool_sources.append(src)
                chunks.append({
                    "filename": doc.metadata.get("filename", ""),
                    "page": p,
                    "page_end": pe,
                    "section": doc.metadata.get("section", ""),
                    "content": doc.page_content[:900],
                })
            return json.dumps({"results": chunks}, ensure_ascii=False)
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
    Search uploaded documents for evidence about ONE focused topic.

    Use for document-specific questions about motivation, methods, experiments,
    results, limitations, definitions, sections, architectures, and frameworks.
    When asking about a specific chapter or section (e.g. '研究方法', 'conclusion',
    '結論', '緒論'), populate section_terms — section-level filtering is applied
    automatically before falling back to semantic search.
    """
    ctx = runtime.context

    if section_terms:
        section_result = await _section_filtered_search(ctx, section_terms)
        if section_result:
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
