"""
test_retrieval_layers.py

四層拆解 + 消融實驗主測試腳本。針對每個測試案例（生活化問法 + 專業改寫問法），
比較「純向量 / 純圖譜(PPR) / 純圖譜(BFS) / RRF融合後」四種設定的 top-K 課程，
並用 _fusion_shadow.fused_search_with_breakdown() 拆解出 RRF 各 Signal
（A/B/A_excl/N/N2/C）對每門候選課程的個別貢獻，再跑一組消融條件（拿掉
Signal C／拿掉 query expansion／拿掉課名 boost／拿掉 A_excl／掃描 RRF_K）
觀察 top-5 排名如何變化。

★ 2026-09-11 重要修正：第一版直接把使用者的完整敘事句丟給 retriever/graph_service，
但實測發現正式流程中 LLM 呼叫 search_courses/ppr_explore 前，會先把敘事句轉成短
關鍵詞（受 system prompt 的 few-shot 範例引導，非強制規則），且 ppr_explore 的
seed 是逗號分隔字串、內部對「每個關鍵詞分別」查詢種子，跟 search_courses 用
「整串合併字串」查一次的機制完全不同。直接餵原始敘事句會嚴重低估 PPR 的真實
表現。因此每個測試案例都改為使用 CASES 中預先「實測捕捉」的真實 LLM 查詢
（見 captured_query/captured_ppr_seeds，附捕捉時間與 debug_agent.py 呼叫紀錄），
而非在測試當下即時呼叫 LLM（避免每次重跑都產生新的 Azure OpenAI 費用與
non-determinism）。若要重新捕捉，執行：
  python scripts/test_course_agent/debug_agent.py "<問句>"
從輸出的【Tool Call 紀錄】複製 search_courses 的 query 與 ppr_explore 的 seed。

執行前提：本地 Qdrant Docker 已啟動且 .env 的 QDRANT_URL 指向它
（見 docs/11-retrieval-evaluation/README.md 的驗證步驟）。

輸出：
  data/test_results/retrieval_eval/<timestamp>_<case_id>.json  （結構化原始資料，
      含 human_eval 欄位骨架，供人工填寫「是否相關／課綱佐證／是否過於進階」）
  data/test_results/retrieval_eval/<timestamp>_report.md        （人類可讀對照表）

用法：
  python scripts/test_course_agent/test_retrieval_layers.py
  python scripts/test_course_agent/test_retrieval_layers.py --case sign_language
  python scripts/test_course_agent/test_retrieval_layers.py --no-ablation
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

# igraph 對不連通的 seed→course 節點對會發 RuntimeWarning（見 _ppr_approx_path），
# 已用 try/except 處理為 None，此處僅消除雜訊，不影響任何邏輯。
warnings.filterwarnings("ignore", message="Couldn't reach some vertices")

_THIS_DIR = Path(__file__).parent
_BACKEND_DIR = _THIS_DIR.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from dotenv import load_dotenv
load_dotenv(_THIS_DIR.parent.parent / ".env")

from app.services import retriever, graph_service

from _fusion_shadow import fused_search_with_breakdown, canary_check, SHADOW_BASE_COMMIT

REPORT_TOP_K = 5
RETRIEVAL_K = 16
OUT_DIR = _THIS_DIR.parent.parent / "data" / "test_results" / "retrieval_eval"

# ── 測試案例 ─────────────────────────────────────────────────────────────────
# question：使用者原始敘事句（記錄用，不直接餵進檢索層）
# captured_query：實測捕捉到的 LLM 呼叫 search_courses 時傳的 query（用於純向量/RRF融合層）
# captured_ppr_seeds：實測捕捉到的 LLM 呼叫 ppr_explore 時傳的 seed，拆成 list（用於純圖譜PPR層）
# captured_tech：LLM 是否額外帶了 tech 參數；若有，代表正式流程其實會走 graph-first
#   tech 分支（tools.py:274-294），完全繞過本測試分析的 RRF 邏輯——本測試仍分析
#   「假設走向量+RRF路徑」的結果，但會在報告中註明這個落差。
CASES: list[dict] = [
    {
        "case_id": "sign_language",
        "label": "手語辨識工具",
        "note": "圖中查無「手語辨識」字面節點，但有 手勢辨識/人體骨架辨識/物件偵測與辨識 等語意相關概念節點；"
                "觀察向量語意擴展能否跨過詞彙鴻溝（score 是否 ≥0.65 觸發 Track A/B）。",
        "variants": {
            "life": {
                "question": "我想做一個可以辨識手語動作的手機App，讓聽障人士能跟一般人溝通，要修哪些課？",
                "captured_query": "手語辨識 手勢辨識 影像辨識 行動應用 機器學習 深度學習",
                "captured_ppr_seeds": ["手語辨識", "手勢辨識", "影像辨識", "行動應用", "機器學習", "深度學習"],
                "captured_tech": None,
                "capture_note": "2026-09-11 debug_agent.py 實測；production 端 ppr_explore 實際回傳 5 筆課程",
            },
            "expert": {
                "question": "我想學手勢辨識、人體骨架辨識，搭配深度學習模型做電腦視覺應用",
                "captured_query": "手勢辨識 人體骨架辨識 深度學習 電腦視覺",
                "captured_ppr_seeds": ["手勢辨識", "人體骨架辨識", "深度學習", "電腦視覺"],
                "captured_tech": "深度學習",
                "capture_note": "2026-09-11 debug_agent.py 實測；LLM 額外帶 tech=深度學習，正式流程會走 "
                                 "graph-first tech 分支（tools.py:274-294），不會真正經過本測試分析的 RRF 路徑；"
                                 "production 端 ppr_explore 實際回傳 9 筆課程",
            },
        },
    },
    {
        "case_id": "receipt_bookkeeping",
        "label": "收據記帳工具",
        "note": "圖中有 工程會計/公司會計/文書屬性辨識 等節點；觀察 Signal A 能否讓資工「文件辨識」"
                "+ 管院「會計」跨學院組合浮現。",
        "variants": {
            "life": {
                "question": "我想寫一個可以拍照辨識收據、自動記帳的App，要學什麼課？",
                "captured_query": "拍照辨識 收據 自動記帳 OCR 文字辨識 資料擷取",
                "captured_ppr_seeds": ["OCR", "電腦視覺", "文字辨識", "資料擷取", "記帳"],
                "captured_tech": None,
                "capture_note": "2026-09-11 debug_agent.py 實測；production 端 ppr_explore 實際回傳 5 筆課程"
                                 "（含「日治時期檔案解讀與利用」等噪音，見報告討論）",
            },
            "expert": {
                "question": "我想學文件影像辨識（OCR）加上複式記帳的會計原理，做自動記帳系統",
                "captured_query": "OCR 文件影像辨識 自動記帳 複式記帳 會計原理",
                "captured_ppr_seeds": ["OCR", "文件影像辨識", "複式記帳", "會計原理", "自動記帳"],
                "captured_tech": "Python",
                "capture_note": "2026-09-11 debug_agent.py 實測；LLM 實際嘗試了 tech=Python 與 tech=OCR 兩次"
                                 "search_courses 呼叫（本測試只取第一次的 query，忽略 tech，分析假設性的 RRF 路徑）；"
                                 "production 端 ppr_explore 實際回傳 8 筆課程",
            },
        },
    },
    {
        "case_id": "fake_news_check",
        "label": "假新聞查核工具",
        "note": "圖中有 自然語言處理/文字探勘/政治性情感 等節點；類比 test_ppr_cross_domain.py 已驗證的"
                "「文學 × NLP」跨域案例，觀察生活化問法能否自動找到這些種子（不靠人工指定）。",
        "variants": {
            "life": {
                "question": "我想做一個能自動判斷網路新聞是不是假的的工具",
                "captured_query": "假新聞 事實查核 資訊素養 資料分析 文本分類",
                "captured_ppr_seeds": ["假新聞", "網路新聞", "訊息辨識", "事實查核"],
                "captured_tech": None,
                "capture_note": "2026-09-11 debug_agent.py 實測；production 端 ppr_explore 實際回報"
                                 "「圖中找不到對應概念節點」——此為圖譜真實限制，非測試方法問題",
            },
            "expert": {
                "question": "我想學自然語言處理和文字探勘，做假新聞偵測與事實查核系統",
                "captured_query": "自然語言處理 文字探勘 假新聞偵測 事實查核",
                "captured_ppr_seeds": ["自然語言處理", "文字探勘", "假新聞偵測", "事實查核"],
                "captured_tech": "自然語言處理",
                "capture_note": "2026-09-11 debug_agent.py 實測；LLM 額外帶 tech=自然語言處理，正式流程會走 "
                                 "graph-first tech 分支，不會真正經過本測試分析的 RRF 路徑；"
                                 "production 端 ppr_explore 實際回傳 8 筆課程",
            },
        },
    },
]

# ── 消融組合（全部透過 _fusion_shadow.fused_search_with_breakdown 的參數開關）─
ABLATIONS: list[dict] = [
    {"name": "baseline",      "params": {}},
    {"name": "no_signal_c",   "params": {"use_signal_c": False}},
    {"name": "no_expansion",  "params": {"use_expansion": False}},
    {"name": "no_name_boost", "params": {"use_name_boost": False}},
    {"name": "no_excl",       "params": {"use_excl": False}},
    {"name": "rrf_k_10",      "params": {"rrf_k": 10}},
    {"name": "rrf_k_30",      "params": {"rrf_k": 30}},
    {"name": "rrf_k_100",     "params": {"rrf_k": 100}},
    {"name": "rrf_k_200",     "params": {"rrf_k": 200}},
]


# ── 四層拆解：各層查詢 + 正規化輸出 ───────────────────────────────────────────

def _pure_vector_layer(query: str, k: int) -> list[dict]:
    """純向量：直接呼叫 retriever.search_courses，無圖擴展、無 Signal N/N2/C。
    query 為 LLM 實際會傳的短查詢（見 CASES 的 captured_query），非原始敘事句。
    """
    hits = retriever.search_courses(query, filters=None, n_results=k, collection="ncu_courses_ug")
    out = []
    for h in hits:
        m = h.get("metadata", {})
        code = m.get("course_code", "")
        if not code:
            code = f"(空payload:{h.get('id', '')})"
            name_zh = "⚠️ 資料品質問題：此筆向量結果的 Qdrant payload 為空"
        else:
            name_zh = m.get("name_zh", "")
        out.append({
            "course_code": code,
            "name_zh": name_zh,
            "dept": m.get("dept", ""),
            "distance": h.get("distance"),
        })
    return out


def _pure_graph_ppr_layer(seed_names: list[str], k: int) -> tuple[list[dict], list[dict]]:
    """純圖譜 PPR：graph_service.ppr_explore，種子用 LLM 實際拆解出的關鍵詞 list
    （對應 tools.py::tool_ppr_explore 把逗號分隔字串 split 後的行為），
    而非把整句話當一個 seed。回傳 (top-k課程, 種子節點清單)。
    """
    seed_ids = _ppr_seed_node_ids(seed_names)
    g = graph_service._g()
    seeds_meta = [
        {
            "node_id": nid,
            "name": g["nodes"].get(nid, {}).get("name", nid),
            "node_type": g["nodes"].get(nid, {}).get("node_type", ""),
        }
        for nid in seed_ids
    ]
    results = graph_service.ppr_explore(seed_names=seed_names, top_k=k, node_type_filter=["Course"])
    out = [
        {"course_code": r["id"], "name_zh": r["name"], "dept": r["dept"], "ppr_score": r["score"]}
        for r in results
    ]
    return out, seeds_meta


def _pure_graph_bfs_layer(query: str, k: int) -> tuple[list[dict], list[str]]:
    """純圖譜 BFS（對照組）：graph_service.explore_by_concept_neighborhood，hops=2。
    LLM 實際流程中沒有觀察到呼叫這個工具，故沿用 captured_query（短查詢）作為輸入，
    僅供對照，不代表正式流程真的會這樣查。
    """
    entry_ids = graph_service._search_concept_nodes(query, top_k=5)
    g = graph_service._g()
    entry_names = [f"{g['nodes'].get(nid, {}).get('name', nid)}[{g['nodes'].get(nid, {}).get('node_type', '?')}]"
                   for nid in entry_ids]
    results = graph_service.explore_by_concept_neighborhood(query, hops=2, top_k=k)
    out = [
        {"course_code": r["id"], "name_zh": r["name"], "dept": r["dept"], "bfs_score": r["score"]}
        for r in results
    ]
    return out, entry_names


# ── 關聯路徑還原 ─────────────────────────────────────────────────────────────

def _direct_signal_paths(course_code: str, seed_concept_names: list[str]) -> list[dict]:
    """Signal A/C 的單跳路徑：課程 get_course_tags() 是否直接含該概念節點名稱。
    query →(向量匹配)→ 概念節點 →(COVERS/TEACHES/COVERS_FIELD)→ 課程。
    """
    tags = graph_service.get_course_tags(course_code)
    tagged = set(tags.get("concepts", [])) | set(tags.get("technologies", [])) | set(tags.get("field_tags", []))
    paths = []
    for name in seed_concept_names:
        if name in tagged:
            paths.append({
                "course_code": course_code,
                "via_node": name,
                "hop_count": 1,
                "path_type": "signal_direct_edge",
                "note": "get_course_tags() 的 concepts/technologies/field_tags 直接包含此節點",
            })
    return paths


def _ppr_seed_node_ids(seed_names: list[str]) -> set[str]:
    """複製 graph_service.ppr_explore() 內第 907-939 行的種子蒐集邏輯（僅取節點 ID 集合，不算權重）。"""
    g = graph_service._g()
    seed_ids: set[str] = set()
    for name in seed_names:
        nodes = {
            nid for nid, score in graph_service._search_concept_nodes_with_scores(name, top_k=8)
            if score >= 0.65
        }
        nodes |= graph_service._find_ppr_seeds([name])
        nodes = {
            s for s in nodes
            if g["nodes"].get(s, {}).get("node_type") != "Field" or graph_service._has_course_edge(s)
        }
        seed_ids |= nodes
    return seed_ids


def _ppr_approx_path(seed_ids: set[str], course_code: str) -> dict | None:
    """用 igraph 最短路徑近似示意 PPR 的種子→課程關聯。
    ⚠️ PPR 是穩態分數，本身沒有單一路徑；此為最短路徑近似示意，非 PPR 實際隨機遊走軌跡。
    """
    G_ig, id_to_idx, idx_to_id = graph_service._load_igraph()
    if G_ig is None or course_code not in id_to_idx:
        return None
    g = graph_service._g()
    course_idx = id_to_idx[course_code]
    best_path_idx = None
    for sid in seed_ids:
        if sid not in id_to_idx:
            continue
        seed_idx = id_to_idx[sid]
        try:
            vpaths = G_ig.get_shortest_paths(seed_idx, to=course_idx, weights="weight", output="vpath")
        except Exception:
            continue
        if vpaths and vpaths[0]:
            path = vpaths[0]
            if best_path_idx is None or len(path) < len(best_path_idx):
                best_path_idx = path
    if not best_path_idx:
        return None
    path_ids = [idx_to_id[i] for i in best_path_idx]
    path_names = [g["nodes"].get(nid, {}).get("name", nid) for nid in path_ids]
    return {
        "course_code": course_code,
        "path_type": "ppr_approx_shortest_path (NOT the actual PPR walk)",
        "path_nodes": path_names,
        "hop_count": len(path_names) - 1,
    }


def _meta_name_dept(entry: dict) -> tuple[str, str]:
    m = entry.get("metadata", {})
    return m.get("name_zh", ""), m.get("dept", "")


# ── 單一問法（一個 variant）的完整拆解 ───────────────────────────────────────

def run_variant(variant: dict, k: int = REPORT_TOP_K, retrieval_k: int = RETRIEVAL_K,
                 run_ablation: bool = True) -> dict:
    question = variant["question"]
    search_query = variant["captured_query"]
    ppr_seeds = variant["captured_ppr_seeds"]

    pure_vector = _pure_vector_layer(search_query, retrieval_k)
    ppr_results, ppr_seeds_meta = _pure_graph_ppr_layer(ppr_seeds, retrieval_k)
    bfs_results, bfs_entry_names = _pure_graph_bfs_layer(search_query, retrieval_k)
    fused = fused_search_with_breakdown(search_query, n=retrieval_k)

    fused_top = fused["ranked"][:k]
    vector_top_codes = [c["course_code"] for c in pure_vector[:k]]
    vector_code_set = set(vector_top_codes)
    fused_code_set = set(fused_top)
    new_in_fused = [c for c in fused_top if c not in vector_code_set]
    lost_from_vector = [c for c in vector_top_codes if c not in fused_code_set]

    # 統一 name/dept 查找表（跨層彙整，供報表與消融結果標名稱用）
    name_lookup: dict[str, dict] = {}
    for c in pure_vector + ppr_results + bfs_results:
        code = c["course_code"]
        if code and code not in name_lookup:
            name_lookup[code] = {"name_zh": c.get("name_zh", ""), "dept": c.get("dept", "")}
    for code, entry in fused["code_meta"].items():
        if code not in name_lookup:
            name_zh, dept = _meta_name_dept(entry)
            name_lookup[code] = {"name_zh": name_zh, "dept": dept}

    # 報表涵蓋的課程集合：純向量/PPR/融合三層 top-k 的聯集
    report_codes = list(dict.fromkeys(vector_top_codes + [c["course_code"] for c in ppr_results[:k]] + fused_top))

    signal_breakdown = {
        code: fused["signals"][code] for code in report_codes if code in fused["signals"]
    }

    # 關聯路徑：Signal A/C 直接邊 + PPR 最短路徑近似
    # 去重：同名概念可能同時是 Concept/Field 等不同節點類型，避免關聯路徑重複列出
    seed_concept_names = list(dict.fromkeys(c["name"] for c in fused["seed_concepts"]))
    graph_relation_paths: list[dict] = []
    for code in report_codes:
        graph_relation_paths.extend(_direct_signal_paths(code, seed_concept_names))
    ppr_seed_ids = {s["node_id"] for s in ppr_seeds_meta}
    for code in [c["course_code"] for c in ppr_results[:k]]:
        p = _ppr_approx_path(ppr_seed_ids, code)
        if p:
            graph_relation_paths.append(p)

    result: dict = {
        "question": question,
        "captured_query": search_query,
        "captured_ppr_seeds": ppr_seeds,
        "captured_tech": variant.get("captured_tech"),
        "capture_note": variant.get("capture_note", ""),
        "pure_vector": {"top5": pure_vector[:k]},
        "pure_graph_ppr": {"seeds_used": ppr_seeds_meta, "top5": ppr_results[:k]},
        "pure_graph_bfs": {"entry_concepts": bfs_entry_names, "top5": bfs_results[:k]},
        "rrf_fused": {
            "expanded_query": fused["expanded_query"],
            "seed_concepts": fused["seed_concepts"],
            "top5": [
                {"course_code": c, **name_lookup.get(c, {"name_zh": "", "dept": ""}),
                 "total_score": fused["signals"].get(c, {}).get("total")}
                for c in fused_top
            ],
        },
        "signal_breakdown": signal_breakdown,
        "graph_relation_paths": graph_relation_paths,
        "new_courses_only_in_fused": new_in_fused,
        "lost_courses_only_in_vector": lost_from_vector,
        "name_lookup": name_lookup,
    }

    if run_ablation:
        result["ablations"] = {}
        for ab in ABLATIONS:
            ab_result = fused_search_with_breakdown(search_query, n=retrieval_k, **ab["params"])
            ab_top = ab_result["ranked"][:k]
            result["ablations"][ab["name"]] = {
                "params": ab["params"],
                "top5": [
                    {"course_code": c, **name_lookup.get(c, {"name_zh": "", "dept": ""})}
                    for c in ab_top
                ],
            }

    # human_eval 骨架，留空供人工填寫
    result["human_eval"] = {
        code: {
            "relevant": None,
            "syllabus_evidence": "",
            "too_advanced_or_duplicate": None,
            "reviewer": "",
            "note": "",
        }
        for code in report_codes
    }

    return result


def run_case(case: dict, k: int, retrieval_k: int, run_ablation: bool) -> dict:
    print(f"\n{'=' * 70}\n  Case: {case['case_id']} — {case['label']}\n{'=' * 70}")
    variants_out = {}
    for variant_name, variant in case["variants"].items():
        print(f"  [{variant_name}] 原問句：{variant['question']}")
        print(f"        → 實測 LLM 查詢：{variant['captured_query']!r}")
        variants_out[variant_name] = run_variant(variant, k=k, retrieval_k=retrieval_k, run_ablation=run_ablation)
    return {
        "case_id": case["case_id"],
        "label": case["label"],
        "note": case.get("note", ""),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_base_commit": SHADOW_BASE_COMMIT,
        "variants": variants_out,
    }


# ── Markdown 報告 ────────────────────────────────────────────────────────────

def _looks_like_raw_qdrant_id(code: str) -> bool:
    """啟發式判斷：課程 code 是否其實是 Qdrant point 的原始數字 ID（而非真正課號）。
    見已知資料品質問題：ncu_courses_ug 約 7% 的點 payload 為空
    （metadata 缺 course_code/name_zh），retriever/tools.py 在 metadata 缺 course_code
    時會 fallback 用 point id 當 code，導致向量搜尋結果混入無法辨識的空白課程。
    """
    return code.isdigit() and len(code) > 12


def _fmt_course_cell(code: str, name_lookup: dict) -> str:
    if not code:
        return "—"
    info = name_lookup.get(code, {})
    name = info.get("name_zh", "")
    if not name and _looks_like_raw_qdrant_id(code):
        return f"⚠️空payload(qdrant_id={code})"
    return f"{code} {name}".strip()


def render_case_markdown(case_result: dict) -> str:
    lines = [f"## {case_result['case_id']} — {case_result['label']}", ""]
    if case_result.get("note"):
        lines.append(f"> {case_result['note']}")
        lines.append("")

    for variant_name, v in case_result["variants"].items():
        lines.append(f"### 問法：{variant_name}")
        lines.append(f"> 原問句：{v['question']}")
        lines.append(f"")
        lines.append(f"**實測 LLM 查詢**（`debug_agent.py` 捕捉，非本腳本即時呼叫）：")
        lines.append(f"- `search_courses(query={v['captured_query']!r}"
                      + (f", tech={v['captured_tech']!r}" if v.get("captured_tech") else "")
                      + ")`")
        lines.append(f"- `ppr_explore(seed={v['captured_ppr_seeds']!r})`")
        if v.get("captured_tech"):
            lines.append(f"- ⚠️ LLM 有帶 `tech` 參數，正式流程會走 graph-first tech 分支"
                          f"（`tools.py:274-294`），完全繞過本報告分析的 RRF 路徑；"
                          f"以下分析是「假設走向量+RRF路徑」的結果，非正式流程實際行為")
        if v.get("capture_note"):
            lines.append(f"- 備註：{v['capture_note']}")
        lines.append("")
        lines.append(f"擴展查詢（expanded_query，由上面的 search_courses query 再經 Layer1 擴展）：`{v['rrf_fused']['expanded_query']}`")
        lines.append("")

        name_lookup = v["name_lookup"]
        pure_codes = [c["course_code"] for c in v["pure_vector"]["top5"]]
        ppr_codes = [c["course_code"] for c in v["pure_graph_ppr"]["top5"]]
        fused_codes = [c["course_code"] for c in v["rrf_fused"]["top5"]]
        max_len = max(len(pure_codes), len(ppr_codes), len(fused_codes), 1)

        lines.append("| 排名 | 純向量 | PPR | RRF融合 | 主要Signal | 關聯路徑摘要 |")
        lines.append("|---|---|---|---|---|---|")
        for i in range(max_len):
            pc = pure_codes[i] if i < len(pure_codes) else ""
            gc = ppr_codes[i] if i < len(ppr_codes) else ""
            fc = fused_codes[i] if i < len(fused_codes) else ""
            dominant = v["signal_breakdown"].get(fc, {}).get("dominant_signal", "") if fc else ""
            paths = [p for p in v["graph_relation_paths"] if p.get("course_code") == fc]
            path_summary = "; ".join(
                p.get("via_node") or "→".join(p.get("path_nodes", [])) for p in paths[:2]
            ) or ""
            marker = "✅" if fc and fc not in {c for c in pure_codes} else ""
            lines.append(
                f"| {i+1} | {_fmt_course_cell(pc, name_lookup)} | {_fmt_course_cell(gc, name_lookup)} | "
                f"{marker}{_fmt_course_cell(fc, name_lookup)} | {dominant or '—'} | {path_summary or '—'} |"
            )
        lines.append("")

        if not ppr_codes:
            lines.append(f"⚠️ PPR 這次真的沒有回傳任何課程（種子 {v['captured_ppr_seeds']} 在圖中"
                          f"都沒有找到對應節點，或分數/連結不足），這是圖譜本身的限制，非測試方法問題。")
            lines.append("")

        if v["new_courses_only_in_fused"]:
            names = ", ".join(_fmt_course_cell(c, name_lookup) for c in v["new_courses_only_in_fused"])
            lines.append(f"✅ **融合後新增**（純向量沒有）：{names}")
        if v["lost_courses_only_in_vector"]:
            names = ", ".join(_fmt_course_cell(c, name_lookup) for c in v["lost_courses_only_in_vector"])
            lines.append(f"❌ **融合後消失**（純向量原有但被擠出 top{REPORT_TOP_K}）：{names}")
        lines.append("")

        if "ablations" in v:
            lines.append("**消融結果**（Top5，比較拿掉單一 Signal / 改變 RRF_K 對排名的影響）：")
            lines.append("")
            lines.append("| 消融條件 | Top5 |")
            lines.append("|---|---|")
            for ab_name, ab in v["ablations"].items():
                names = "、".join(_fmt_course_cell(c["course_code"], name_lookup) for c in ab["top5"])
                lines.append(f"| {ab_name} | {names} |")
            lines.append("")

        lines.append("**Layer1 種子概念節點**（`_search_concept_nodes_with_scores`，score≥0.65 才進 Track A/B）：")
        seeds = v["rrf_fused"]["seed_concepts"]
        if seeds:
            for s in seeds[:10]:
                lines.append(f"- {s['name']} [{s['node_type']}] score={s['score']}")
        else:
            lines.append("- （無 Concept/Technology/Field/Competency 節點命中）")
        lines.append("")
        lines.append("**人工判斷**（待填）：")
        lines.append("")
        lines.append("| 課程 | 相關？ | 課綱佐證 | 過於進階/重複？ | 備註 |")
        lines.append("|---|---|---|---|---|")
        for code in v["human_eval"]:
            lines.append(f"| {_fmt_course_cell(code, name_lookup)} |  |  |  |  |")
        lines.append("")

    return "\n".join(lines)


def render_full_report(all_cases: list[dict]) -> str:
    lines = [
        "# 檢索分層測試報告（v2：改用實測 LLM 查詢）",
        "",
        f"執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"影子複製基準 commit：`{SHADOW_BASE_COMMIT}`",
        "",
        "四層定義：純向量（`retriever.search_courses`，無圖擴展）／"
        "純圖譜 PPR（`graph_service.ppr_explore`，alpha=0.85）／"
        "純圖譜 BFS（`graph_service.explore_by_concept_neighborhood`，hops=2，對照組）／"
        "RRF 融合後（`tool_search_courses` 的影子複製，RRF_K=60，含 Signal A/B/A_excl/N/N2/C）。",
        "",
        "⚠️ **v2 修正**：純向量與純圖譜PPR層改用「實測捕捉的 LLM 真實查詢」（見各案例的"
        "「實測 LLM 查詢」區塊），而非直接把使用者原始敘事句餵給檢索層——v1 版本這樣做會嚴重"
        "低估 PPR 的真實表現（PPR 的 seed 是逐一分開查詢，敘事句當一個 seed 幾乎不可能命中）。",
        "",
        "⚠️ PPR 欄位的「關聯路徑」為 igraph 最短路徑近似示意，非 PPR 實際隨機遊走軌跡。",
        "",
        "---",
        "",
    ]
    for case_result in all_cases:
        lines.append(render_case_markdown(case_result))
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="四層拆解 + 消融實驗測試腳本")
    parser.add_argument("--case", action="append", help="只跑指定 case_id（可重複指定），預設跑全部")
    parser.add_argument("--no-ablation", action="store_true", help="跳過消融實驗，加快單題除錯")
    parser.add_argument("--no-canary", action="store_true", help="跳過開頭的 canary 一致性檢查")
    parser.add_argument("--k", type=int, default=REPORT_TOP_K, help="報表顯示筆數（預設 5）")
    parser.add_argument("--retrieval-k", type=int, default=RETRIEVAL_K, help="底層檢索筆數（預設 16）")
    parser.add_argument("--yes", action="store_true", help="canary 不一致時仍強制繼續（非互動環境用）")
    args = parser.parse_args()

    if not args.no_canary:
        print("── Canary 一致性檢查 ──")
        ok = canary_check(verbose=True)
        if not ok:
            if not args.yes:
                print("\n⚠️ 影子複製與生產邏輯不一致，結果可能不可信。是否仍要繼續？(y/N): ", end="")
                if input().strip().lower() != "y":
                    sys.exit(1)
            else:
                print("\n⚠️ 影子複製與生產邏輯不一致，但 --yes 已指定，強制繼續。")
        print()

    cases = CASES
    if args.case:
        wanted = set(args.case)
        cases = [c for c in CASES if c["case_id"] in wanted]
        if not cases:
            print(f"[錯誤] 找不到 case_id：{args.case}；可用選項：{[c['case_id'] for c in CASES]}")
            sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results = []
    for case in cases:
        result = run_case(case, k=args.k, retrieval_k=args.retrieval_k, run_ablation=not args.no_ablation)
        all_results.append(result)
        json_path = OUT_DIR / f"{timestamp}_{case['case_id']}.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
        print(f"  → {json_path}")

    report_md = render_full_report(all_results)
    report_path = OUT_DIR / f"{timestamp}_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n[報告已輸出] {report_path}")


if __name__ == "__main__":
    main()
