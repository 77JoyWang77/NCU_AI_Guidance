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
    _emit_stage_sync,
    run_search_report,
    set_query_expander_llm,
)
from app.rag import aget_document_language as _aget_document_language

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
    """
    return await run_search_report(
        query=query,
        ctx=runtime.context,
        sub_queries=sub_queries,
        display_intent=display_intent,
        keyword_query=keyword_query,
        semantic_query=semantic_query,
        section_terms=section_terms,
        use_hyde=use_hyde,
    )


@tool
async def detect_document_language(runtime: ToolRuntime[AgentContext]) -> str:
    """Detect primary language of uploaded documents."""
    ctx = runtime.context
    _emit_stage_sync(ctx.on_stage, "偵測文件語言")
    lang = await _aget_document_language(ctx.document_ids or None)
    return json.dumps({"language": lang}, ensure_ascii=False)


@tool
def get_document_metadata(runtime: ToolRuntime[AgentContext]) -> str:
    """
    Get detailed metadata for the selected documents.

    Returns filename and a short abstract preview. Use this when the user asks
    about document properties such as title or subject area.
    """
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument

    ctx = runtime.context
    with PdfSessionLocal() as db:
        docs = db.query(PdfDocument).filter(PdfDocument.id.in_(ctx.document_ids or [])).all()
        result = []
        for doc in docs:
            result.append({
                "id": doc.id,
                "filename": doc.filename,
                "abstract_preview": (doc.abstract_text or "")[:400],
            })
        return json.dumps(result, ensure_ascii=False)


@tool
async def search_by_section(section: str, runtime: ToolRuntime[AgentContext]) -> str:
    """
    Retrieve chunks from a specific document section by name.

    Use this when the user asks about a specific chapter or section — e.g.
    '研究方法章節', 'conclusion', '結論', '緒論' — and you want section-level
    precision without relying purely on keyword search.

    section: section name in Chinese or English (e.g. '研究方法', 'methods',
             '結論', 'conclusion', '文獻回顧', 'related_work')
    """
    from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
    from app.rag import (
        get_vectorstore, get_dense_vectorstore, aget_document_language,
        RETRIEVAL_K, search_documents,
    )

    ctx = runtime.context
    canonical = _resolve_section(section)

    must: list = []
    if ctx.document_ids:
        must.append(FieldCondition(key="metadata.document_id", match=MatchAny(any=[str(did) for did in ctx.document_ids])))
    must.append(FieldCondition(key="metadata.section", match=MatchValue(value=canonical)))
    qdrant_filter = Filter(must=must)

    lang = await aget_document_language(ctx.document_ids)
    vs = get_dense_vectorstore() if lang == "en" else get_vectorstore()
    hits = await vs.asimilarity_search(section, k=RETRIEVAL_K, filter=qdrant_filter)

    if not hits:
        aliases = _SECTION_ALIASES.get(canonical, [section])
        chunks, _sources = await search_documents(
            queries=[section, canonical, " ".join(aliases)],
            document_ids=ctx.document_ids,
            top_n=6,
            lang=lang,
        )
        if not chunks:
            return json.dumps({"results": [], "message": f"No chunks found for section '{section}' (resolved: '{canonical}')."}, ensure_ascii=False)
        return json.dumps({"results": chunks[:6], "fallback": "heading_keyword"}, ensure_ascii=False)

    chunks = [
        {"filename": doc.metadata.get("filename", ""), "page": doc.metadata.get("page"),
         "section": doc.metadata.get("section", ""), "content": doc.page_content[:900]}
        for doc in hits[:6]
    ]
    return json.dumps({"results": chunks, "fallback": "none"}, ensure_ascii=False)


TOOLS = [
    search_report,
    search_by_section,
    get_document_metadata,
]

__all__ = [
    "AgentContext",
    "SearchInput",
    "TOOLS",
    "detect_document_language",
    "get_document_metadata",
    "run_search_report",
    "search_by_section",
    "search_report",
    "set_query_expander_llm",
]
