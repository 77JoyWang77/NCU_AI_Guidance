"""
_fusion_shadow.py

測試專用「影子複製」：重現 backend/app/services/tools.py::tool_search_courses()
的 Layer1（Query Expansion）/ Layer2（多路向量搜尋）/ Layer3（RRF 融合 + boost）邏輯，
但把 Layer3 的加總過程拆成逐 Signal 記錄，並把原本寫死在函式內的常數
（RRF_K / NAME_EXACT_BOOST / PARTIAL_BOOST）與各 Signal 開關（是否啟用 query expansion／
Signal C／A_excl／課名 boost）改為可調參數，供：

  1. 對同一查詢拆解「哪個 Signal 貢獻了哪門課的哪部分分數」
  2. 消融實驗（拿掉某個 Signal、改變 RRF_K）觀察 top-K 排名變化

★ 不修改任何生產程式碼，只讀取並呼叫 tools.py / graph_service.py / retriever.py
  裡既有的公開／內部函式。

★ 影子複製基準：git commit 688ef56bc755f4f1bfa84ac8d99147d0f00a3907
  （backend/app/services/tools.py:245-562 的 tool_search_courses，
  含 tech-first graph 分支以外的 Layer1-3 主邏輯）。
  若之後 tools.py 這段邏輯有修改，本檔案會與生產行為脫節——
  執行 `python scripts/test_course_agent/_fusion_shadow.py` 或呼叫 canary_check()
  可以偵測是否已經脫節（全開參數下 top-5 course_code 是否仍與
  tool_search_courses() 完全一致）。

★ 範圍限制（刻意省略，不影響消融/拆解目的）：
  - tech 參數的 graph-first 分支（tools.py:274-294）未複製，
    因為它會完全繞過 RRF，與本檔案要拆解的融合邏輯無關。
  - course_type / topic_tag filter 條件未複製（測試查詢不需要）。

用法：
  from _fusion_shadow import fused_search_with_breakdown, canary_check
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).parent
_BACKEND_DIR = _THIS_DIR.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_THIS_DIR.parent.parent / ".env")

from app.services import retriever
from app.services import graph_service
from app.services import tools as prod_tools
from app.services.graph_service import _search_concept_nodes_with_scores
from app.services.tools import _resolve_name

SHADOW_BASE_COMMIT = "688ef56bc755f4f1bfa84ac8d99147d0f00a3907"

_EXPAND_TYPES = {"Concept", "Technology", "Field", "Competency"}
_SIGNAL_C_SCORE_THRESHOLD = 0.65   # tools.py:317（Track B 收錄門檻）
_EXCL_DIST_THRESHOLD = 0.65        # tools.py:446（A_excl 距離門檻）
_SIGNAL_NAMES = ("A", "B", "A_excl", "N", "N2", "C")


def fused_search_with_breakdown(
    query: str,
    *,
    dept: str | None = None,
    college: str | None = None,
    student_college: str | None = None,
    is_grad: bool = False,
    exclude_grad_only: bool = True,
    n: int = 16,
    rrf_k: int = 60,
    name_exact_boost: float = 0.15,
    partial_boost: float = 0.05,
    use_expansion: bool = True,
    use_signal_c: bool = True,
    use_excl: bool = True,
    use_name_boost: bool = True,
) -> dict:
    """回傳：
    {
      "query", "expanded_query",
      "seed_concepts":       [{node_id,name,node_type,score}, ...]  # Track A 命中的概念節點
      "direct_course_items": [{node_id,name,score}, ...]            # Track B（Signal C 候選）
      "signals":   {course_code: {A,B,A_excl,N,N2,C,total,dominant_signal}},
      "code_meta": {course_code: 原始 retriever 結果 dict（含 metadata/distance）},
      "exact_match_codes": set(),
      "ranked":    [course_code, ...]（exact_match 置頂 + 語意排序，前 n 筆）,
      "params":    本次呼叫實際生效的參數（供記錄消融條件）,
    }
    """
    dept = _resolve_name(dept)
    college = _resolve_name(college)
    student_college = _resolve_name(student_college)

    g = graph_service._g()

    # ── Layer 1：Query Expansion（雙軌）── tools.py:296-329 ──────────────────
    scored_nodes = _search_concept_nodes_with_scores(query, top_k=25)

    seen_term_names: set[str] = {query.lower()}
    extra_terms: list[str] = []
    seen_course_names: set[str] = set()
    direct_course_items: list[tuple[str, float]] = []
    seed_concepts: list[dict] = []

    for nid, score in scored_nodes:
        nd = g["nodes"].get(nid, {})
        ntype = nd.get("node_type", "")
        name = nd.get("name", "")
        if ntype in _EXPAND_TYPES:
            seed_concepts.append({"node_id": nid, "name": name, "node_type": ntype, "score": score})
            if name and name.lower() not in seen_term_names:
                extra_terms.append(name)
                seen_term_names.add(name.lower())
        elif ntype == "Course" and score >= _SIGNAL_C_SCORE_THRESHOLD:
            if name and name not in seen_course_names:
                if dept and nd.get("dept", "") != dept:
                    continue
                if college and nd.get("college", "") != college:
                    continue
                seen_course_names.add(name)
                direct_course_items.append((nid, score))

    if use_expansion and extra_terms:
        expanded_query = (query + " " + " ".join(extra_terms[:5])).strip()
    else:
        expanded_query = query

    # ── Layer 2：Qdrant filters + 多路向量搜尋 ── tools.py:331-421 ────────────
    conditions: list[dict] = []
    if dept:
        conditions.append({"dept": {"$eq": dept}})
    if college:
        conditions.append({"college": {"$eq": college}})
    if exclude_grad_only and not is_grad:
        conditions.append({"is_grad_only": {"$eq": False}})
    if student_college:
        _col_map = retriever._load_college_map()
        depts_in_college = [d for d, c in _col_map.items() if c == student_college]
        student_college_or: list[dict] = [
            {"is_open_to_all_undergrad": {"$eq": True}},
            {"college_include":          {"$contains": student_college}},
        ]
        for _d in depts_in_college:
            student_college_or.append({"dept_include": {"$contains": _d}})
        conditions.append({"$or": student_college_or})

    if len(conditions) == 0:
        filters = None
    elif len(conditions) == 1:
        filters = conditions[0]
    else:
        filters = {"$and": conditions}

    collection = "ncu_courses_grad" if is_grad else "ncu_courses_ug"

    # Signal A：擴展查詢 + filters
    results_a = retriever.search_courses(
        expanded_query, filters=filters, n_results=n * 3, collection=collection
    )

    # Signal B：原始查詢 + filters（僅在 expanded != query 時才查，同生產邏輯）
    if expanded_query != query:
        results_b = retriever.search_courses(
            query, filters=filters, n_results=n * 3, collection=collection
        )
    else:
        results_b = []

    # Signal A_excl / B_excl：排除系限補回
    results_excl: list[dict] = []
    if use_excl and student_college:
        _col_map_excl = retriever._load_college_map()
        depts_in_college = [d for d, c in _col_map_excl.items() if c == student_college]
        excl_must_not: list[dict] = (
            [{"dept_exclude": {"$contains": d}} for d in depts_in_college]
            + [{"dept_exclude":    {"$contains": student_college}}]
            + [{"college_exclude": {"$contains": student_college}}]
        )
        excl_base_filter: dict = {"is_open_with_exclusions": {"$eq": True}}
        if exclude_grad_only and not is_grad:
            excl_base_filter = {"$and": [
                {"is_open_with_exclusions": {"$eq": True}},
                {"is_grad_only": {"$eq": False}},
            ]}
        results_excl = retriever.search_courses(
            expanded_query, filters=excl_base_filter, must_not_conds=excl_must_not,
            n_results=n * 2, collection=collection,
        )
        if expanded_query != query:
            results_excl_b = retriever.search_courses(
                query, filters=excl_base_filter, must_not_conds=excl_must_not,
                n_results=n * 2, collection=collection,
            )
            results_excl = results_excl + results_excl_b

    # ── Layer 3：逐 Signal 記錄（不加總成單一分數）── tools.py:423-548 ───────
    signals: dict[str, dict[str, float]] = {}
    code_meta: dict[str, dict] = {}

    def _bump(code: str, sig: str, val: float, meta: dict) -> None:
        d = signals.setdefault(code, {s: 0.0 for s in _SIGNAL_NAMES})
        d[sig] = d.get(sig, 0.0) + val
        code_meta.setdefault(code, meta)

    for rank, r in enumerate(results_a, 1):
        code = r.get("metadata", {}).get("course_code", "") or r.get("id", "")
        if not code:
            continue
        _bump(code, "A", 1.0 / (rrf_k + rank), r)

    if results_b:
        for rank, r in enumerate(results_b, 1):
            code = r.get("metadata", {}).get("course_code", "") or r.get("id", "")
            if not code:
                continue
            _bump(code, "B", 1.0 / (rrf_k + rank), r)

    results_excl_filtered = [
        r for r in results_excl if r.get("distance", 1.0) <= _EXCL_DIST_THRESHOLD
    ]
    for rank, r in enumerate(results_excl_filtered, 1):
        code = r.get("metadata", {}).get("course_code", "") or r.get("id", "")
        if not code:
            continue
        _bump(code, "A_excl", 1.0 / (rrf_k + rank), r)

    # Signal N / N2：課名 boost
    exact_match_codes: set[str] = set()
    if use_name_boost:
        exact_name_hits = retriever.get_courses_by_name(query, collection=collection)
        for r in exact_name_hits:
            meta = r.get("metadata", {})
            code = meta.get("course_code", "") or r.get("id", "")
            if not code:
                continue
            if student_college:
                c_include  = meta.get("college_include", [])
                d_include  = meta.get("dept_include", [])
                is_open    = meta.get("is_open_to_all_undergrad", False)
                is_excl    = meta.get("is_open_with_exclusions", False)
                c_exclude  = meta.get("college_exclude", [])
                d_exclude  = meta.get("dept_exclude", [])
                _col_map_n = retriever._load_college_map()
                depts_in_scn = [d for d, c in _col_map_n.items() if c == student_college]
                depts_ok_n = any(d in d_include for d in depts_in_scn)
                if not (is_open or student_college in c_include or depts_ok_n or is_excl):
                    continue
                if student_college in c_exclude or student_college in d_exclude:
                    continue
                if any(d in d_exclude for d in depts_in_scn):
                    continue
            _bump(code, "N", name_exact_boost, r)
            exact_match_codes.add(code)

        for code, r in list(code_meta.items()):
            if code in exact_match_codes:
                continue
            meta = r.get("metadata", {})
            name_zh = meta.get("name_zh", "")
            if not name_zh or query not in name_zh:
                continue
            if college and meta.get("college", "") != college:
                continue
            if dept and meta.get("dept", "") != dept:
                continue
            _bump(code, "N2", partial_boost, r)

    # Signal C：圖語意直達課程
    if use_signal_c:
        for course_code, sig_score in direct_course_items:
            if "[已停開]" in g["nodes"].get(course_code, {}).get("name", ""):
                continue
            boost = sig_score / (rrf_k + 1)
            if course_code in code_meta:
                _bump(course_code, "C", boost, code_meta[course_code])
            else:
                hits = retriever.get_courses_by_code(course_code, collection=collection)
                if hits:
                    if student_college:
                        meta = hits[0].get("metadata", {})
                        c_include  = meta.get("college_include", [])
                        d_include  = meta.get("dept_include", [])
                        is_open    = meta.get("is_open_to_all_undergrad", False)
                        is_excl    = meta.get("is_open_with_exclusions", False)
                        c_exclude  = meta.get("college_exclude", [])
                        d_exclude  = meta.get("dept_exclude", [])
                        _col_map   = retriever._load_college_map()
                        depts_in_sc = [d for d, c in _col_map.items() if c == student_college]
                        depts_ok   = any(d in d_include for d in depts_in_sc)
                        passes_positive = (
                            is_open or student_college in c_include or depts_ok or is_excl
                        )
                        if not passes_positive:
                            continue
                        if student_college in c_exclude:
                            continue
                        if any(d in d_exclude for d in depts_in_sc):
                            continue
                        if student_college in d_exclude:
                            continue
                    _bump(course_code, "C", boost, hits[0])

    # 總分 + 主要貢獻 Signal
    for code, d in signals.items():
        d["total"] = sum(d[s] for s in _SIGNAL_NAMES)
        dominant = max(_SIGNAL_NAMES, key=lambda s: d[s])
        d["dominant_signal"] = dominant if d[dominant] > 0 else None

    ranked_all = sorted(signals, key=lambda c: signals[c]["total"], reverse=True)
    exact_ranked = [c for c in ranked_all if c in exact_match_codes and c in code_meta]
    semantic_ranked = [
        c for c in ranked_all
        if c not in exact_match_codes and c in code_meta and not c.startswith("SC")
    ][:n]
    ranked = exact_ranked + semantic_ranked

    return {
        "query": query,
        "expanded_query": expanded_query,
        "seed_concepts": seed_concepts,
        "direct_course_items": [
            {"node_id": nid, "name": g["nodes"].get(nid, {}).get("name", ""), "score": score}
            for nid, score in direct_course_items
        ],
        "signals": signals,
        "code_meta": code_meta,
        "exact_match_codes": exact_match_codes,
        "ranked": ranked,
        "params": {
            "rrf_k": rrf_k,
            "name_exact_boost": name_exact_boost,
            "partial_boost": partial_boost,
            "use_expansion": use_expansion,
            "use_signal_c": use_signal_c,
            "use_excl": use_excl,
            "use_name_boost": use_name_boost,
        },
    }


def canary_check(queries: list[str] | None = None, n: int = 16, verbose: bool = True) -> bool:
    """全開參數下，影子複製 top-5 course_code 是否與正式 tool_search_courses() 完全一致。

    用來偵測 tools.py::tool_search_courses 是否已經改動、本檔案已經過期。
    不一致時請重新對照 tools.py:245-562 更新本檔案的 Layer1-3 邏輯。
    """
    if queries is None:
        queries = ["機器學習", "資料結構", "會計"]

    all_ok = True
    for q in queries:
        shadow = fused_search_with_breakdown(q, n=n)
        shadow_top5 = shadow["ranked"][:5]

        prod_results = prod_tools.tool_search_courses(q, n=n)
        prod_top5 = [r.get("course_code", "") for r in prod_results][:5]

        ok = shadow_top5 == prod_top5
        all_ok = all_ok and ok
        if verbose:
            status = "OK" if ok else "MISMATCH"
            print(f"[canary][{status}] query={q!r}")
            print(f"  shadow: {shadow_top5}")
            print(f"  prod  : {prod_top5}")
    return all_ok


if __name__ == "__main__":
    print(f"影子複製基準 commit: {SHADOW_BASE_COMMIT}")
    ok = canary_check()
    if ok:
        print("\n✅ 全部一致，影子複製與生產邏輯同步。")
    else:
        print("\n⚠️ 發現不一致，請重新比對 backend/app/services/tools.py:245-562 後更新本檔案。")
        sys.exit(1)
