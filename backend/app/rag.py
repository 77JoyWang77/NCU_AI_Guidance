"""RAG search layer: Qdrant client, language detection, chunk counting, and search.

This is a focused subset of the source rag/ package — ingestion is excluded.
Only the functions needed by app.tools.search_core and app.tools.rag_tool are provided.
"""
import asyncio
import hashlib
import logging
import re
from typing import TypedDict

from langchain_community.document_compressors.flashrank_rerank import FlashrankRerank
from langchain_openai import AzureOpenAIEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    Modifier,
    Rrf,
    RrfQuery,
    SparseVectorParams,
    VectorParams,
)

from app.pdf_config import pdf_settings

logger = logging.getLogger(__name__)

VECTOR_SIZE = 3072
DENSE_NAME = "dense"
SPARSE_NAME = "sparse"
RETRIEVAL_K = 10
RERANK_TOP_N = 4
RERANK_MAX = 12

# ── Singletons ─────────────────────────────────────────────────────────────────

_dense_embeddings: AzureOpenAIEmbeddings | None = None
_vectorstore: QdrantVectorStore | None = None
_dense_vectorstore: QdrantVectorStore | None = None
_reranker: FlashrankRerank | None = None
_qdrant_client: QdrantClient | None = None
_async_qdrant_client: AsyncQdrantClient | None = None


def _collection() -> str:
    return pdf_settings.pdf_qdrant_collection


def _build_client() -> QdrantClient:
    kwargs: dict = {"url": pdf_settings.qdrant_url, "timeout": 15}
    if pdf_settings.qdrant_api_key.get_secret_value():
        kwargs["api_key"] = pdf_settings.qdrant_api_key.get_secret_value()
    return QdrantClient(**kwargs)


def _build_async_client() -> AsyncQdrantClient:
    kwargs: dict = {"url": pdf_settings.qdrant_url, "timeout": 15}
    if pdf_settings.qdrant_api_key.get_secret_value():
        kwargs["api_key"] = pdf_settings.qdrant_api_key.get_secret_value()
    return AsyncQdrantClient(**kwargs)


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = _build_client()
    return _qdrant_client


def get_async_qdrant_client() -> AsyncQdrantClient:
    global _async_qdrant_client
    if _async_qdrant_client is None:
        _async_qdrant_client = _build_async_client()
    return _async_qdrant_client


def get_dense_embeddings() -> AzureOpenAIEmbeddings:
    global _dense_embeddings
    if _dense_embeddings is None:
        _dense_embeddings = AzureOpenAIEmbeddings(
            azure_deployment=pdf_settings.azure_embedding_deployment,
            azure_endpoint=pdf_settings.azure_openai_endpoint,
            api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
            api_version=pdf_settings.azure_openai_api_version,
        )
    return _dense_embeddings


def _ensure_collection(client: QdrantClient) -> None:
    name = _collection()
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config={DENSE_NAME: VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={SPARSE_NAME: SparseVectorParams(modifier=Modifier.IDF)},
    )


def get_vectorstore() -> QdrantVectorStore:
    global _vectorstore
    if _vectorstore is None:
        client = _build_client()
        _ensure_collection(client)
        _vectorstore = QdrantVectorStore(
            client=client,
            collection_name=_collection(),
            embedding=get_dense_embeddings(),
            sparse_embedding=FastEmbedSparse(model_name="Qdrant/bm25"),
            vector_name=DENSE_NAME,
            sparse_vector_name=SPARSE_NAME,
            retrieval_mode=RetrievalMode.HYBRID,
        )
    return _vectorstore


def get_dense_vectorstore() -> QdrantVectorStore:
    global _dense_vectorstore
    if _dense_vectorstore is None:
        client = _build_client()
        _ensure_collection(client)
        _dense_vectorstore = QdrantVectorStore(
            client=client,
            collection_name=_collection(),
            embedding=get_dense_embeddings(),
            vector_name=DENSE_NAME,
            retrieval_mode=RetrievalMode.DENSE,
        )
    return _dense_vectorstore


def get_reranker() -> FlashrankRerank:
    global _reranker
    if _reranker is None:
        _reranker = FlashrankRerank(top_n=RERANK_MAX)
    return _reranker


# ── Language detection ─────────────────────────────────────────────────────────

def _is_cjk(c: str) -> bool:
    cp = ord(c)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0xF900 <= cp <= 0xFAFF
    )


def _lang_from_text(text: str) -> str:
    cjk = sum(1 for c in text if _is_cjk(c))
    ascii_alpha = sum(1 for c in text if c.isascii() and c.isalpha())
    total = cjk + ascii_alpha
    if total == 0:
        return "zh"
    return "en" if cjk / total < 0.15 else "zh"


def get_document_language(document_ids: list[int] | None = None) -> str:
    client = get_qdrant_client()
    scroll_filter = None
    if document_ids:
        scroll_filter = Filter(
            must=[FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in document_ids]),
            )]
        )
    results, _ = client.scroll(
        collection_name=_collection(),
        scroll_filter=scroll_filter,
        limit=50,
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        return "unknown"
    sample = " ".join(r.payload.get("page_content", "") for r in results if r.payload)
    return _lang_from_text(sample)


async def aget_document_language(document_ids: list[int] | None = None) -> str:
    client = get_async_qdrant_client()
    scroll_filter = None
    if document_ids:
        scroll_filter = Filter(
            must=[FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in document_ids]),
            )]
        )
    results, _ = await client.scroll(
        collection_name=_collection(),
        scroll_filter=scroll_filter,
        limit=50,
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        return "unknown"
    sample = " ".join(r.payload.get("page_content", "") for r in results if r.payload)
    return _lang_from_text(sample)


# ── Chunk counting ──────────────────────────────────────────────────────────────

def count_document_chunks(document_ids: list[int] | None) -> int:
    client = get_qdrant_client()
    qdrant_filter = None
    if document_ids:
        qdrant_filter = Filter(
            must=[FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in document_ids]),
            )]
        )
    result = client.count(collection_name=_collection(), count_filter=qdrant_filter, exact=True)
    return result.count


async def acount_document_chunks(document_ids: list[int] | None) -> int:
    client = get_async_qdrant_client()
    qdrant_filter = None
    if document_ids:
        qdrant_filter = Filter(
            must=[FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in document_ids]),
            )]
        )
    result = await client.count(collection_name=_collection(), count_filter=qdrant_filter, exact=True)
    return result.count


# ── Page quality filters (inlined from rag.cleaning) ──────────────────────────

_COVER_PAGE_DEFINITIVE = (
    "大專學生研究計畫研究成果報告",
    "執行計畫學生",
    "學生計畫編號",
)
_COVER_PAGE_MARKERS = (
    "國家科學及技術委員會補助",
    "大專學生研究計畫",
    "研究成果報告",
)
_REFERENCES_MARKERS = (
    "參考文獻", "參考書目", "引用文獻",
    "Bibliography", "References", "REFERENCES",
)
_REFERENCES_PATTERN = re.compile(
    r"^\s*(?:[\[【\(（]?\d+[\]】\)）\.]|[a-zA-Z][a-zA-Z\-]+,)",
    re.MULTILINE,
)
_INLINE_BULLETED_REFERENCE_RE = re.compile(
    r"(?:^|\s)[✧*•]\s*[A-Z][A-Za-z'\-]+,\s+[A-Z]"
)
_ZH_REFERENCES_PATTERN = re.compile(
    r"[一-鿿]{1,6}[，,：]\s*[《〈]"
    r"|[，,]\s*頁\s*\d"
    r"|[，,]\s*\d{4}\s*年[）)]"
    r"|（\d{4}\s*年\s*[），]"
)
_BULLETED_REFERENCE_RE = re.compile(
    r"^\s*(?:[✧*•\-]\s*)?[A-Z][A-Za-z'\-]+,\s+[A-Z]",
    re.MULTILINE,
)
_MATH_UNICODE = frozenset(
    "∑∫∂∇∞≤≥≠≈∝αβγδεζηθλμνξπρστφψωΩΔΓΛΣΦΨ"
    "⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉"
)
_LATEX_DELIMITER_RE = re.compile(
    r'^\s*(?:\$\$|\\\[|\\\]|\\begin\{[^}]+\}|\\end\{[^}]+\}|-{3,})\s*$'
)


def _is_cover_page(text: str) -> bool:
    if any(phrase in text for phrase in _COVER_PAGE_DEFINITIVE):
        return True
    if not any(marker in text for marker in _COVER_PAGE_MARKERS):
        return False
    for line in text.splitlines():
        cjk_count = sum(1 for c in line if '一' <= c <= '鿿')
        if cjk_count >= 25:
            return False
    return True


def _is_references_page(text: str) -> bool:
    stripped = text.lstrip()
    for marker in _REFERENCES_MARKERS:
        if stripped.startswith(marker) or stripped.startswith(f"# {marker}") or stripped.startswith(f"## {marker}"):
            return True
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 4:
        return len(_INLINE_BULLETED_REFERENCE_RE.findall(text)) >= 3
    if len(_INLINE_BULLETED_REFERENCE_RE.findall(text)) >= 3:
        return True
    entry_starts = sum(
        1 for l in lines
        if (
            _REFERENCES_PATTERN.search(l)
            or _BULLETED_REFERENCE_RE.search(l)
            or _ZH_REFERENCES_PATTERN.search(l)
        )
    )
    if entry_starts >= 3:
        return True
    return entry_starts / len(lines) >= 0.5


def _is_table_or_formula_heavy(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 4:
        return False
    pipe_lines = sum(
        1 for l in lines
        if l.count("|") >= 2 and not re.search(r'\\[\(\[]|\\frac|\\leq|\\geq', l)
    )
    if pipe_lines / len(lines) >= 0.35:
        return True
    content_lines = [l for l in lines if not _LATEX_DELIMITER_RE.match(l)]
    if not content_lines:
        return False
    short_lines = sum(1 for l in content_lines if len(l) <= 15)
    if short_lines / len(content_lines) >= 0.55:
        return True
    combined = "".join(lines)
    if combined:
        math_density = sum(1 for c in combined if c in _MATH_UNICODE) / len(combined)
        if math_density >= 0.04:
            return True
    return False


# ── Search ─────────────────────────────────────────────────────────────────────

class RetrievedChunk(TypedDict):
    filename: str
    page: int | str
    page_end: int | str
    section: str
    content: str
    is_low_quality: bool


_WEIGHTED_RRF = RrfQuery(rrf=Rrf(weights=[2.0, 1.0]))


def _chunk_key(content: str) -> str:
    return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()


async def search_documents(
    queries: list[str],
    document_ids: list[int] | None = None,
    top_n: int | None = None,
    lang: str | None = None,
    exclude_chunk_keys: set[str] | None = None,
    weighted_rrf: bool = False,
) -> tuple[list[RetrievedChunk], list[str]]:
    """Multi-query search → deduplicate → rerank."""
    effective_lang = lang or await aget_document_language(document_ids)

    qdrant_filter = None
    if document_ids:
        qdrant_filter = Filter(
            must=[FieldCondition(
                key="metadata.document_id",
                match=MatchAny(any=[str(did) for did in document_ids]),
            )]
        )

    seen_content: set[str] = set()
    all_results = []
    # Run all queries in parallel; for mixed-language docs, run both dense and hybrid then deduplicate
    if effective_lang == "mixed":
        _dense_vs = get_dense_vectorstore()
        _hybrid_vs = get_vectorstore()
        _fusion = _WEIGHTED_RRF if weighted_rrf else None
        _dense_hits, _hybrid_hits = await asyncio.gather(
            asyncio.gather(*[_dense_vs.asimilarity_search(q, k=RETRIEVAL_K, filter=qdrant_filter) for q in queries]),
            asyncio.gather(*[_hybrid_vs.asimilarity_search(q, k=RETRIEVAL_K, filter=qdrant_filter, hybrid_fusion=_fusion) for q in queries]),
        )
        hit_lists = list(_dense_hits) + list(_hybrid_hits)
    elif effective_lang == "en":
        _vs = get_dense_vectorstore()
        hit_lists = await asyncio.gather(*[_vs.asimilarity_search(q, k=RETRIEVAL_K, filter=qdrant_filter) for q in queries])
    else:
        _vs = get_vectorstore()
        _fusion = _WEIGHTED_RRF if weighted_rrf else None
        hit_lists = await asyncio.gather(*[_vs.asimilarity_search(q, k=RETRIEVAL_K, filter=qdrant_filter, hybrid_fusion=_fusion) for q in queries])
    for hits in hit_lists:
        for doc in hits:
            _sec = doc.metadata.get("section", "")
            if _sec in ("references", "參考文獻"):
                continue
            if _is_cover_page(doc.page_content) or _is_references_page(doc.page_content):
                continue
            if exclude_chunk_keys and _chunk_key(doc.page_content) in exclude_chunk_keys:
                continue
            key = _chunk_key(doc.page_content)
            if key not in seen_content:
                seen_content.add(key)
                all_results.append(doc)

    if not all_results:
        return [], []

    effective_top_n = min(top_n or RERANK_TOP_N, RERANK_MAX)
    reranker = get_reranker()
    best_score: dict[str, float] = {}
    best_doc: dict[str, object] = {}
    # Run reranking queries in parallel with per-query timeout to avoid blocking on large chunks
    _RERANK_TIMEOUT = 8.0
    rerank_results = []
    for coro in asyncio.as_completed([
        asyncio.wait_for(
            asyncio.to_thread(reranker.compress_documents, all_results, q),
            timeout=_RERANK_TIMEOUT,
        )
        for q in queries[:3]
    ]):
        try:
            rerank_results.append(await coro)
        except asyncio.TimeoutError:
            logger.warning("rerank: timed out for one query, skipping")
    for docs in rerank_results:
        for doc in docs:
            key = _chunk_key(doc.page_content)
            score = doc.metadata.get("relevance_score", 0.0)
            if score > best_score.get(key, -1):
                best_score[key] = score
                best_doc[key] = doc

    is_heavy: dict[str, bool] = {
        key: _is_table_or_formula_heavy(doc.page_content)
        for key, doc in best_doc.items()
    }

    def _rank_key(d):
        key = _chunk_key(d.page_content)
        return (is_heavy.get(key, False), -best_score[key])

    ranked = sorted(best_doc.values(), key=_rank_key)
    all_results = ranked[:effective_top_n]

    for doc in all_results:
        key = _chunk_key(doc.page_content)
        doc.metadata["is_low_quality"] = is_heavy.get(key, False)

    chunks: list[RetrievedChunk] = []
    sources: list[str] = []
    seen_sources: set[str] = set()
    for doc in all_results:
        filename = doc.metadata.get("filename", "Unknown")
        page = doc.metadata.get("page", "?")
        page_end = doc.metadata.get("page_end", page)
        page_num = int(page) + 1 if page != "?" else "?"
        page_end_num = int(page_end) + 1 if page_end != "?" else page_num
        section = doc.metadata.get("section", "unknown")
        low_q = doc.metadata.get("is_low_quality", False)
        chunks.append(RetrievedChunk(
            filename=filename, page=page_num, page_end=page_end_num,
            section=section, content=doc.page_content, is_low_quality=low_q,
        ))
        source = (
            f"{filename} p.{page_num}-{page_end_num}"
            if page_end_num != page_num else
            f"{filename} p.{page_num}"
        )
        if source not in seen_sources:
            seen_sources.add(source)
            sources.append(source)

    return chunks, sources
