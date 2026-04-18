"""
retriever.py

ChromaDB 向量搜尋介面，對應五個 collection：
  ncu_courses_ug / ncu_courses_grad / ncu_credit_programs / ncu_departments / ncu_teachers
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chromadb
from openai import AzureOpenAI

ROOT = Path(__file__).parent.parent.parent.parent  # project root
CHROMA_DIR = ROOT / "data" / "processed" / "chroma_db"


@lru_cache(maxsize=1)
def _get_chroma() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


@lru_cache(maxsize=1)
def _get_oai() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )


def _embed(text: str) -> list[float]:
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    resp = _get_oai().embeddings.create(model=deployment, input=[text])
    return resp.data[0].embedding


def _col(name: str):
    return _get_chroma().get_collection(name)


# ── 公開介面 ─────────────────────────────────────────────────────────────────

def search_courses(
    query: str,
    filters: Optional[dict] = None,
    n_results: int = 10,
    collection: str = "ncu_courses_ug",
) -> list[dict]:
    """
    向量搜尋課程。

    filters 範例（ChromaDB where 語法）：
      {"type": "必修"}
      {"college": "資訊電機學院"}
      {"required_year": 1, "required_sem": 1}
      {"tools": {"$contains": "PyTorch"}}
      {"$and": [{"college": "資訊電機學院"}, {"type": "必修"}]}
    """
    embedding = _embed(query)
    kwargs: dict = {"query_embeddings": [embedding], "n_results": n_results,
                    "include": ["documents", "metadatas", "distances"]}
    if filters:
        kwargs["where"] = filters

    col = _col(collection)
    res = col.query(**kwargs)
    return _format(res)


def search_programs(query: str, n_results: int = 5) -> list[dict]:
    embedding = _embed(query)
    res = _col("ncu_credit_programs").query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    return _format(res)


def search_departments(query: str, n_results: int = 5) -> list[dict]:
    embedding = _embed(query)
    res = _col("ncu_departments").query(
        query_embeddings=[embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    return _format(res)


def search_teachers(
    query: str,
    filters: Optional[dict] = None,
    n_results: int = 8,
) -> list[dict]:
    embedding = _embed(query)
    kwargs: dict = {"query_embeddings": [embedding], "n_results": n_results,
                    "include": ["documents", "metadatas", "distances"]}
    if filters:
        kwargs["where"] = filters

    res = _col("ncu_teachers").query(**kwargs)
    return _format(res)


def get_teacher_by_name(name: str) -> list[dict]:
    """直接用名字查教師（不走向量）"""
    res = _col("ncu_teachers").get(
        where={"name": name},
        include=["documents", "metadatas"],
    )
    return [
        {"document": d, "metadata": m, "distance": 0.0}
        for d, m in zip(res["documents"], res["metadatas"])
    ]


def get_courses_by_code(code: str, collection: str = "ncu_courses_ug") -> list[dict]:
    """直接用課號查課程（不走向量）"""
    res = _col(collection).get(
        where={"course_code": code},
        include=["documents", "metadatas"],
    )
    return [
        {"document": d, "metadata": m, "distance": 0.0}
        for d, m in zip(res["documents"], res["metadatas"])
    ]


# ── 格式化輸出 ───────────────────────────────────────────────────────────────

def _format(res: dict) -> list[dict]:
    """把 ChromaDB query 結果攤平成 list[dict]"""
    if not res or not res.get("ids"):
        return []
    ids = res["ids"][0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    return [
        {
            "id": ids[i],
            "document": docs[i],
            "metadata": metas[i],
            "distance": round(dists[i], 4),
        }
        for i in range(len(ids))
    ]
