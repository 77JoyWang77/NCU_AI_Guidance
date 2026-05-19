"""
test_ppr_cross_domain.py — PPR 跨域能力測試（含種子權重平衡優化後對比）

對每個查詢顯示：
  - 種子節點分布（按概念名稱分組，顯示各概念節點數）
  - 每門結果課程的 PPR 分數
  - 課程連結的 Concept/Technology/Field 節點（★ 表示與種子直接關聯）
  - alpha=0.85 單一組結果（不再對比 0.75，改為比較舊/新版本差異）

輸出：data/test_results/<timestamp>_ppr_cross_domain.md

用法：
  python scripts/test_ppr_cross_domain.py
"""

import sys
import statistics
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import graph_service

# ── 測試案例 ──────────────────────────────────────────────────────────────────
# 舊案例：驗證種子平衡修正效果（與前次結果對比）
OLD_CASES = [
    {
        "title": "【回歸】ML × 生物資訊",
        "seeds": ["機器學習", "生物資訊"],
        "note": "前次：生物資訊被壓制，結果幾乎等同單種子ML → 修正後應出現生物相關課程",
    },
    {
        "title": "【回歸】永續發展 × 工程",
        "seeds": ["永續發展", "工程"],
        "note": "前次：工程354個節點佔絕對優勢，永續消失 → 修正後應看到永續相關課程",
    },
    {
        "title": "【回歸】統計 × 經濟",
        "seeds": ["統計學", "經濟學"],
        "note": "前次：客家政治經濟進階噪音排第一 → 修正後噪音應下降",
    },
]

# 新案例：驗證跨域能力與新場景
NEW_CASES = [
    {
        "title": "【新】AI × 金融工程",
        "seeds": ["機器學習", "金融工程"],
        "note": "預期：量化投資、演算法交易、風險模型相關課程",
    },
    {
        "title": "【新】機器學習 × 統計學",
        "seeds": ["機器學習", "統計學"],
        "note": "統計 27 個種子 vs ML 7 個，平衡修正後應更均衡",
    },
    {
        "title": "【新】資料庫 × 企業管理",
        "seeds": ["資料庫", "企業管理"],
        "note": "預期：IS/MIS、ERP 相關課程",
    },
    {
        "title": "【新】量子計算 × 演算法",
        "seeds": ["量子計算", "演算法"],
        "note": "圖稀疏域測試，量子計算課程稀少",
    },
    {
        "title": "【新】文學 × 自然語言處理",
        "seeds": ["文學", "自然語言處理"],
        "note": "跨院極端異質：人文 × 資工，預期：數位人文、語料庫語言學",
    },
    {
        "title": "【新】影像處理 × 醫學（驗證成功案例）",
        "seeds": ["影像處理", "醫學"],
        "note": "前次已成功，確認修正後結果不退步",
    },
]

TEST_CASES = OLD_CASES + NEW_CASES
TOP_K  = 20
ALPHAS = [0.85]  # 種子平衡修正是主要變數，固定 alpha 觀察


# ── Helper：取課程連結的概念節點 ───────────────────────────────────────────────
def get_course_tags(nid: str, g: dict) -> dict:
    """回傳課程出向邊連到的 Concept/Technology/Field 節點名稱。"""
    concepts, techs, fields = [], [], []
    for tgt, rel in g["out"].get(nid, []):
        nd = g["nodes"].get(tgt, {})
        name = nd.get("name", "")
        if not name:
            continue
        if rel == "COVERS":
            concepts.append(name)
        elif rel == "TEACHES":
            techs.append(name)
        elif rel == "COVERS_FIELD":
            fields.append(name)
    return {"concepts": concepts, "techs": techs, "fields": fields}


_SEED_VECTOR_THRESHOLD = 0.65

def get_seed_node_info(seed_names: list[str], g: dict) -> dict:
    """回傳 PPR 實際使用的種子節點，按概念名稱分組（與修改後的 ppr_explore 一致）。"""
    name_to_nodes: dict[str, list[dict]] = {}
    for name in seed_names:
        nodes: set[str] = {
            nid for nid, score in graph_service._search_concept_nodes_with_scores(name, top_k=8)
            if score >= _SEED_VECTOR_THRESHOLD
        }
        nodes |= graph_service._find_ppr_seeds([name])
        nodes = {
            s for s in nodes
            if g["nodes"].get(s, {}).get("node_type") != "Field"
            or graph_service._has_course_edge(s)
        }
        entries = []
        for sid in nodes:
            nd = g["nodes"].get(sid, {})
            entries.append({
                "id":   sid,
                "name": nd.get("name", sid),
                "type": nd.get("node_type", ""),
            })
        entries.sort(key=lambda x: x["name"])
        name_to_nodes[name] = entries
    return name_to_nodes


def mark_seed_relation(tags: dict, seed_names: list[str], seed_node_names: set[str]) -> list[str]:
    """判斷課程標籤與種子的關係，回傳帶 ★ 標記的標籤清單。"""
    all_tags = tags["concepts"] + tags["techs"] + tags["fields"]
    marked = []
    for t in all_tags:
        tl = t.lower()
        is_seed = any(
            tl == sn.lower() or tl in sn.lower() or sn.lower() in tl
            for sn in seed_node_names
        )
        marked.append(f"★{t}" if is_seed else t)
    return marked


def run_ppr(seeds: list[str], alpha: float, g: dict) -> list[dict]:
    results = graph_service.ppr_explore(
        seed_names=seeds,
        top_k=TOP_K,
        alpha=alpha,
        node_type_filter=["Course"],
    )
    for r in results:
        tags = get_course_tags(r["id"], g)
        r["_tags"] = tags
    return results


# ── 格式化輸出 ─────────────────────────────────────────────────────────────────
def fmt_case(case: dict, g: dict) -> list[str]:
    seeds = case["seeds"]
    lines = []
    lines.append(f"\n---\n")
    lines.append(f"## {case['title']}")
    lines.append(f"> 種子：`{'、'.join(seeds)}`  \n> {case['note']}")

    # 種子節點（按概念分組顯示，讓讀者看到平衡效果）
    name_to_nodes = get_seed_node_info(seeds, g)
    total_seeds = sum(len(v) for v in name_to_nodes.values())
    seed_node_names: set[str] = {e["name"] for entries in name_to_nodes.values() for e in entries}

    lines.append(f"\n### 種子節點分布（概念數 {len(name_to_nodes)}，總節點 {total_seeds}）\n")
    for concept_name, entries in name_to_nodes.items():
        n_concepts = len(name_to_nodes)
        per_node_w = 1.0 / (n_concepts * len(entries)) if entries else 0
        lines.append(
            f"**{concept_name}**（{len(entries)} 個節點，每節點權重 {per_node_w:.4f}，"
            f"本概念總權重 {1/n_concepts:.2f}）"
        )
        # 最多顯示 6 個節點避免「工程」那種列 300 行
        shown = entries[:6]
        for e in shown:
            lines.append(f"  - {e['name']} [{e['type']}]")
        if len(entries) > 6:
            lines.append(f"  - *…（共 {len(entries)} 個，僅顯示前 6）*")

    # PPR 結果
    for alpha in ALPHAS:
        results = run_ppr(seeds, alpha, g)
        lines.append(f"\n### 結果（α={alpha}，{len(results)} 筆，gap_filter 後）\n")

        if not results:
            lines.append("*無結果*")
            continue

        scores = [r["score"] for r in results]
        lines.append(
            f"> score 範圍：{min(scores):.4f} ~ {max(scores):.4f}，"
            f"mean={statistics.mean(scores):.4f}，"
            f"stdev={statistics.stdev(scores) if len(scores) > 1 else 0:.4f}"
        )
        lines.append("")
        lines.append("| # | 課程名稱 | 系所 | score | ★種子直接關聯 | 其他概念/技術 |")
        lines.append("|---|---------|------|-------|-------------|-------------|")

        for i, r in enumerate(results, 1):
            tags = r["_tags"]
            marked = mark_seed_relation(tags, seeds, seed_node_names)
            seed_tags  = [t[1:] for t in marked if t.startswith("★")]
            other_tags = [t for t in marked if not t.startswith("★")]

            dept      = r.get("dept", "") or ""
            score_str = f"{r['score']:.4f}"
            seed_str  = "、".join(seed_tags[:5])  if seed_tags  else "（間接）"
            other_str = "、".join(other_tags[:4]) if other_tags else ""

            lines.append(f"| {i} | {r['name']} | {dept} | {score_str} | {seed_str} | {other_str} |")

    return lines


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    print("載入知識圖譜...")
    g = graph_service._g()
    print(f"  節點數：{len(g['nodes'])}，邊數：{sum(len(v) for v in g['out'].values())}")

    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"# PPR 跨域能力測試報告（種子權重平衡優化後）")
    lines.append(f"\n執行時間：{now}  ")
    lines.append(f"參數：TOP_K={TOP_K}，alpha={ALPHAS[0]}  ")
    lines.append(f"★ = 課程的 Concept/Technology/Field 節點與種子直接名稱關聯  \n")
    lines.append(f"> **優化說明**：每個概念名稱均分 `1/n_concepts` 的重置權重，再平均分給旗下節點。  ")
    lines.append(f"> 「工程」(354 節點) 與「永續發展」(3 節點) 各佔 50% 影響力，而非被節點數主導。  ")
    lines.append(f"> **閱讀指引**：看各概念的「本概念總權重」是否接近 1/n_concepts，確認平衡生效。  ")

    for case in TEST_CASES:
        print(f"執行：{case['title']}...")
        lines.extend(fmt_case(case, g))

    out_dir  = ROOT / "data" / "test_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{ts}_ppr_cross_domain.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ 輸出：{out_path}")


if __name__ == "__main__":
    main()
