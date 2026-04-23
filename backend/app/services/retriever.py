"""
retriever.py

ChromaDB 向量搜尋介面，對應五個 collection：
  ncu_courses_ug / ncu_courses_grad / ncu_credit_programs / ncu_departments / ncu_teachers
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chromadb
from openai import AzureOpenAI

ROOT = Path(__file__).parent.parent.parent.parent  # project root
CHROMA_DIR = ROOT / "data" / "processed" / "chroma_db"
_ELIGIBILITY_PATH  = ROOT / "data" / "processed" / "course_eligibility.json"
_COLLEGE_MAP_PATH  = ROOT / "data" / "processed" / "dept_college_map.json"


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


@lru_cache(maxsize=1)
def _load_eligibility_index() -> dict[str, dict]:
    if not _ELIGIBILITY_PATH.exists():
        return {}
    data = json.loads(_ELIGIBILITY_PATH.read_text(encoding="utf-8"))
    return {entry["course_code"]: entry for entry in data if entry.get("course_code")}


def get_course_eligibility(course_code: str) -> dict:
    """回傳課程的完整修課資格資料（含 access_rules），直接從 JSON 讀取。"""
    return _load_eligibility_index().get(course_code, {})


@lru_cache(maxsize=1)
def _load_college_map() -> dict[str, str]:
    if not _COLLEGE_MAP_PATH.exists():
        return {}
    return json.loads(_COLLEGE_MAP_PATH.read_text(encoding="utf-8"))


def get_dept_college(dept: str) -> str:
    """回傳系所所屬學院名稱，查無則回傳空字串。"""
    return _load_college_map().get(dept, "")


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
      {"type": {"$eq": "必修"}}
      {"$and": [{"college": {"$eq": "資訊電機學院"}}, {"type": {"$eq": "必修"}}]}
      {"tools": {"$contains": "PyTorch"}}
    """
    embedding = _embed(query)
    col = _col(collection)
    kwargs: dict = {"query_embeddings": [embedding], "n_results": n_results,
                    "include": ["documents", "metadatas", "distances"]}
    if filters:
        kwargs["where"] = filters

    try:
        res = col.query(**kwargs)
        return _format(res)
    except Exception:
        # ChromaDB 1.x 在 where 過濾後 0 筆匹配時拋例外；去掉 filter 後做純語意搜尋
        if filters:
            try:
                kwargs_nf = {k: v for k, v in kwargs.items() if k != "where"}
                res = col.query(**kwargs_nf)
                results = _format(res)
                # 後處理：保留 dept/college/type 最相近的結果
                return results
            except Exception:
                pass
        return []


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


def get_courses_by_dept_type(
    dept: str,
    course_type: str = "選修",
    collection: str = "ncu_courses_ug",
    limit: int = 200,
) -> list[dict]:
    """直接用 dept + type 精確過濾，回傳全部課程（不走向量，不受 n_results 上限）。"""
    res = _col(collection).get(
        where={"$and": [{"dept": {"$eq": dept}}, {"type": {"$eq": course_type}}]},
        include=["documents", "metadatas"],
        limit=limit,
    )
    docs   = res.get("documents") or []
    metas  = res.get("metadatas") or []
    ids    = res.get("ids") or []
    return [
        {"id": ids[i], "document": docs[i], "metadata": metas[i], "distance": 0.0}
        for i in range(len(ids))
    ]


def get_courses_by_name(
    name: str,
    collection: str = "ncu_courses_ug",
    also_grad: bool = True,
) -> list[dict]:
    """用課程名稱精確比對，同時搜大學部與研究所（供課程消歧義用）。"""
    results = []
    cols = [collection]
    if also_grad and collection == "ncu_courses_ug":
        cols.append("ncu_courses_grad")
    for col_name in cols:
        res = _col(col_name).get(
            where={"name_zh": {"$eq": name}},
            include=["documents", "metadatas"],
        )
        docs  = res.get("documents") or []
        metas = res.get("metadatas") or []
        ids   = res.get("ids") or []
        results.extend(
            {"id": ids[i], "document": docs[i], "metadata": metas[i], "distance": 0.0}
            for i in range(len(ids))
        )
    return results


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
