"""
test_search_comparison.py

直接呼叫工具函式（非透過 LLM），比較 search_courses 現有策略（Signal A+B）
與不同 concept 提取策略的差異。

用途：
  1. 觀察 _search_concept_nodes_with_scores 對各 query 的分數分布（D1 threshold 依據）
  2. 比較 固定 top_k=3 vs 動態 threshold 會提取哪些 concept
  3. 顯示各 concept 在 Qdrant payload 中直接命中的課程數（Signal D 可行性）
  4. 比較 Strategy A+B（現有）vs Strategy C（圖 BFS）的重疊與差異

執行方式（在 backend/ 目錄下）：
  python -m scripts.test_search_comparison              # 跑所有預設 query
  python -m scripts.test_search_comparison "機器學習"   # 只跑指定 query
  python -m scripts.test_search_comparison --ppr        # PPR E2-a 驗證
"""

import sys
import os
import io
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# 載入專案根目錄的 .env（main.py 才會載，直接跑腳本需自行載入）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from app.services.tools import tool_search_courses
    from app.services.graph_service import (
        _search_concept_nodes,
        _search_concept_nodes_with_scores,
        explore_by_concept_neighborhood,
        _g,
        _find_ppr_seeds,
        ppr_explore,
    )
    from app.services.retriever import _get_qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchAny
except ImportError as e:
    print(f"[錯誤] 無法 import 模組：{e}")
    print("請在 backend/ 目錄下執行：python -m scripts.test_search_comparison")
    sys.exit(1)


TEST_QUERIES = [
    # ── 原有測試 ───────────────────────────────────────────────────────────
    ("資料結構",        "STEM 精確"),
    ("微分方程",        "STEM 多系共享"),
    ("機器學習",        "跨域 AI"),
    ("深度學習",        "跨域 AI"),
    ("資料科學",        "領域標籤（D1 目標）"),
    ("人工智慧",        "泛用詞"),
    ("類神經網路",      "中文→英文概念"),
    ("GIS",             "縮寫"),
    ("量子力學",        "理學院"),
    ("語言學",          "文學院"),
    ("社會研究方法",    "社科"),
    ("倫理",            "通識目標"),
    ("元宇宙",          "難以命中"),
    ("統計",            "跨院廣泛"),
    # ── 模糊概念／跨域詞 ───────────────────────────────────────────────────
    ("畫圖",            "極度模糊：繪畫 vs CAD vs 視覺化"),
    ("立體概念",        "模糊：3D 建模 vs 幾何 vs 雕塑"),
    ("社會實踐",        "模糊：服務學習 vs 社會學 vs 實習"),
    ("企業視野",        "模糊：策略 vs 管理 vs 商業"),
    ("創業",            "跨院：商管 + 工程 + 社會"),
    # ── 高中生常用詞彙 ─────────────────────────────────────────────────────
    ("矩陣",            "高中數學→線性代數"),
    ("化學公式",        "高中化學→大學化學橋接"),
    ("數學證明",        "高中→大學數學思維"),
    ("宋代詩詞",        "高中國文→中文系課程"),
    ("唐朝人物",        "高中歷史→歷史系"),
    ("英文口語",        "高中英文→語言課程"),
]

PPR_TESTS = [
    ("機器學習",                          "course",     "單種子 AI"),
    ("機器學習,深度學習,神經網路",        "course",     "多種子 AI"),
    ("機器學習",                          "instructor", "AI 相關教授"),
    ("系統",                              "course",     "太模糊觀察雜訊"),
    ("法律與政府研究所",                  "course",     "E2-a 目標：圖中不存在"),
    ("微積分",                            "course",     "基礎學科"),
]

SCORE_THRESHOLDS = [0.50, 0.65, 0.75, 0.80]


# ── Tee：同時輸出到 stdout 和 StringIO ────────────────────────────────────────

class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


# ── Payload 直接比對（Signal D 預覽）────────────────────────────────────────

def _count_concept_payload_matches(concept_name: str, collection: str = "ncu_courses_ug") -> int:
    """計算 Qdrant payload 中 concepts 欄位包含該 concept 名稱的課程數量。
    concepts 欄位為 list[str]，用 MatchAny 匹配。
    count() 需要 keyword index，改用 scroll 全掃（測試用途，效能可接受）。
    """
    try:
        client = _get_qdrant()
        scroll_filter = Filter(must=[
            FieldCondition(key="concepts", match=MatchAny(any=[concept_name]))
        ])
        total = 0
        offset = None
        while True:
            records, next_offset = client.scroll(
                collection_name=collection,
                scroll_filter=scroll_filter,
                limit=100,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            total += len(records)
            if next_offset is None:
                break
            offset = next_offset
        return total
    except Exception:
        return -1


# ── 格式化 ────────────────────────────────────────────────────────────────────

def _divider(title: str, char: str = "=", width: int = 65):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


# ── 主要測試：concept 分數分布 + 策略比較 ─────────────────────────────────────

def run_search_comparison(query: str, label: str = "", n: int = 8):
    _divider(f"Query: {query}  [{label}]")

    # ── 1. Concept 節點分數分布（新）────────────────────────────────────────
    scored = _search_concept_nodes_with_scores(query, top_k=25)
    g = _g()

    print(f"\n[Concept 節點分數分布（top_k=25）]")
    print(f"  {'節點名稱':<30} {'類型':<14} {'score':>6}  {'payload_hits':>12}  threshold 收錄")
    print(f"  {'-'*30} {'-'*14} {'-'*6}  {'-'*12}  {'-'*30}")

    for nid, score in scored:
        nd = g["nodes"].get(nid, {})
        name = nd.get("name", nid)
        ntype = nd.get("node_type", "?")
        payload_hits = _count_concept_payload_matches(name)
        hits_str = str(payload_hits) if payload_hits >= 0 else "error"

        # 計算哪些 threshold 會收錄
        included = [f"≥{t}" for t in SCORE_THRESHOLDS if score >= t]
        excluded = [f"≥{t}" for t in SCORE_THRESHOLDS if score < t]
        threshold_str = f"收錄：{','.join(included) or '無'}"
        if excluded:
            threshold_str += f"  排除：{','.join(excluded)}"

        marker = "▶" if score >= 0.65 else " "
        print(f"  {marker} {name:<28} [{ntype:<12}] {score:>6.4f}  {hits_str:>12}  {threshold_str}")

    # threshold 分析摘要
    print(f"\n  [各 threshold 收錄 concept 數]")
    for t in SCORE_THRESHOLDS:
        count = sum(1 for _, s in scored if s >= t)
        names_in = [g["nodes"].get(nid, {}).get("name", nid) for nid, s in scored if s >= t]
        print(f"    ≥{t}: {count} 個 → {', '.join(names_in[:5]) or '（無）'}")

    # 現有 top_k=3 固定策略
    old_top3 = [g["nodes"].get(nid, {}).get("name", nid) for nid, _ in scored[:3]]
    print(f"\n  [現有固定 top_k=3 提取]：{', '.join(old_top3) or '（無）'}")

    # ── 2. 現有策略 Signal A+B+C ────────────────────────────────────────────
    try:
        results_ab = tool_search_courses(query, n=n)
    except Exception as e:
        print(f"\n[Strategy A+B+C 執行失敗] {e}")
        results_ab = []

    print(f"\n[Strategy A+B+C: Qdrant 雙軌擴展 + Signal C 注入，共 {len(results_ab)} 筆]")
    for r in results_ab:
        src = " *graph*" if r.get("source") == "graph_tech" else ""
        print(f"  {r.get('course_code',''):<10} {r.get('name_zh',''):<28} {r.get('dept','')}{src}")

    # ── 3. 圖概念直達路徑（D2 preview, 入口概念分析）──────────────────────
    # 顯示 BFS 入口：_search_concept_nodes 找到的前 5 個概念節點
    from app.services.graph_service import _search_concept_nodes
    entry_ids = _search_concept_nodes(query, top_k=5)
    entry_info = []
    for eid in entry_ids:
        en = g["nodes"].get(eid, {})
        entry_info.append(f"{en.get('name', eid)}[{en.get('node_type','?')}]")

    try:
        results_c = explore_by_concept_neighborhood(query, hops=2, top_k=n * 2)
    except Exception as e:
        print(f"\n[Strategy C BFS 執行失敗] {e}")
        results_c = []

    print(f"\n[Strategy C: 圖 BFS（D2 preview, hops=2），共 {len(results_c)} 筆]")
    print(f"  入口概念：{', '.join(entry_info) or '（無）'}")
    for r in results_c[:n]:
        print(f"  {r.get('id',''):<10} {r.get('name',''):<28} {r.get('dept',''):<22} score={r.get('score',0)}")
    if not results_c:
        print("  （無命中 — COVERS 邊可能不足）")

    # ── 4. 重疊分析 ──────────────────────────────────────────────────────────
    codes_ab = {r.get("course_code", "") for r in results_ab if r.get("course_code")}
    codes_c  = {r.get("id", "") for r in results_c[:n] if r.get("id")}
    overlap     = codes_ab & codes_c
    only_graph  = codes_c - codes_ab
    only_qdrant = codes_ab - codes_c

    print(f"\n[重疊分析]")
    print(f"  共同命中：{len(overlap)} 筆")
    if only_graph:
        print(f"  只有圖命中（D2 可增加）：{len(only_graph)} 筆 → {only_graph}")
    else:
        print(f"  只有圖命中：0 筆（Signal C 無新增價值）")
    print(f"  只有 Qdrant 命中：{len(only_qdrant)} 筆")


def run_ppr_test(seed: str, focus: str, label: str):
    _divider(f"PPR | seed={seed!r}  focus={focus}  [{label}]", char="-")
    seed_list = [s.strip() for s in seed.replace("、", ",").replace("，", ",").split(",")]
    found = _find_ppr_seeds(seed_list)
    print(f"  _find_ppr_seeds 回傳：{len(found)} 個節點 ID")
    if not found:
        print("  → 圖中無對應節點，E2-a 應提示 LLM 改策略")
        return
    type_filter_map = {
        "course":     ["Course"],
        "instructor": ["Instructor"],
        "dept":       ["Department", "DeptGroup", "CollegeBachelorProgram"],
    }
    results = ppr_explore(seed_names=seed_list, top_k=10,
                          node_type_filter=type_filter_map.get(focus, ["Course"]))
    print(f"  PPR 結果：{len(results)} 筆")
    for r in results[:8]:
        print(f"    [{r['node_type']:<12}] {r['name']:<30} score={r['score']}")


def main():
    args = sys.argv[1:]

    # 決定輸出模式
    run_ppr = "--ppr" in args
    if run_ppr:
        args.remove("--ppr")

    # 設定 markdown 輸出路徑
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "ppr" if run_ppr else "concept_threshold"
    out_dir = Path(__file__).parent.parent / "data" / "test_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{timestamp}_{suffix}.md"

    buf = io.StringIO()
    tee = _Tee(sys.stdout, buf)
    original_stdout = sys.stdout
    sys.stdout = tee

    try:
        if run_ppr:
            print(f"# PPR Seed Confidence 測試（E2-a）")
            print(f"執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            print("=" * 65)
            for seed, focus, label in PPR_TESTS:
                run_ppr_test(seed, focus, label)
        else:
            print(f"# Concept Threshold 分析 & 策略比較")
            print(f"執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"\n**threshold 說明**：▶ = score ≥ 0.65（D1 建議門檻）")
            print(f"**payload_hits**：Qdrant `ncu_courses_ug` 中 concepts 欄位直接包含該 concept 名稱的課程數")
            print(f"**Signal D 判斷**：payload_hits > 0 且 score 高時，可考慮直接 scroll 補充")

            if args:
                for q in args:
                    run_search_comparison(q)
            else:
                print(f"\n執行所有預設 query（共 {len(TEST_QUERIES)} 個）...")
                for query, label in TEST_QUERIES:
                    run_search_comparison(query, label)

            print("\n\n" + "=" * 65)
            print("  提示：執行 --ppr 測試 PPR seed confidence（E2-a）")
            print(f"  範例：python -m scripts.test_search_comparison --ppr")
            print("=" * 65)
    finally:
        sys.stdout = original_stdout

    # 寫入 markdown
    content = buf.getvalue()
    # 把 plain text 包在 code block 讓 markdown 好讀
    md_content = f"```\n{content}\n```\n"
    out_path.write_text(md_content, encoding="utf-8")
    print(f"\n[輸出已儲存] {out_path}")


if __name__ == "__main__":
    main()
