"""
test_2hop_similar.py — 測試 2-hop 概念擴展對相似課推薦的影響

比較：
  A（現有）：Course → COVERS/TEACHES → Concept → (反向) → Course
  B（2-hop）：+ Concept → SIMILAR_TO → Concept' → (反向) → Course（折扣 0.5）

隨機抽樣 + 指定課程，輸出 data/test_results/<ts>_2hop_similar.md
"""

import sys
import random
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import graph_service

# ── 參數 ──────────────────────────────────────────────────────────────────────
TOP_N          = 15       # 各方法回傳筆數
HOP2_DISCOUNT  = 0.5      # 2-hop SIMILAR_TO 邊的分數折扣（1-hop=1.0，2-hop=0.5）
RANDOM_SEED    = 42
N_RANDOM       = 20       # 隨機抽樣課程數

# 指定測試課程（確保涵蓋不同領域）
FIXED_COURSES = [
    # CS / AI（概念豐富）
    "機器學習",
    "深度學習",
    "資料結構",
    "計算機網路",
    # 數理（中等概念）
    "統計學",
    "微積分",
    "量子力學",
    # 工程（中等）
    "電磁學",
    "電力系統",
    "材料科學",
    # 生命科學
    "生物資訊學",
    "生物化學",
    # 商管
    "財務管理",
    "行銷管理",
    # 人文社科（概念稀疏）
    "英文寫作",
    "法律概論",
    "社會學",
    # 跨域 / 稀疏
    "石油能源",
    "永續發展",
    "數位人文",
]

# ── 核心：1-hop ───────────────────────────────────────────────────────────────
def similar_1hop(course_name: str, g: dict, top_n: int = TOP_N) -> tuple[list[dict], set[str]]:
    """現有邏輯（同 search_courses_by_concept_cluster）。回傳 (results, concept_ids)"""
    seed_courses = graph_service.get_course_info(course_name)
    if not seed_courses:
        return [], set()

    seed_concepts: set[str] = set()
    for sc in seed_courses:
        for tgt, rel in g["out"].get(sc["id"], []):
            if rel in ("COVERS", "TEACHES"):
                seed_concepts.add(tgt)

    if not seed_concepts:
        return [], set()

    seed_ids = {sc["id"] for sc in seed_courses}
    score: dict[str, float] = {}
    for cid in seed_concepts:
        for src, rel in g["in"].get(cid, []):
            if rel in ("COVERS", "TEACHES") and src not in seed_ids:
                if g["nodes"].get(src, {}).get("node_type") == "Course":
                    score[src] = score.get(src, 0) + 1.0

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:top_n]
    results = []
    for cid, s in ranked:
        n = g["nodes"].get(cid, {})
        results.append({
            "id": cid, "name": n.get("name", cid),
            "dept": n.get("dept", ""), "score": s,
            "via": "1hop",
        })
    return results, seed_concepts


# ── 核心：2-hop（1-hop + SIMILAR_TO 擴展）────────────────────────────────────
def similar_2hop(course_name: str, g: dict, top_n: int = TOP_N) -> tuple[list[dict], dict]:
    """
    在 1-hop 基礎上，沿 SIMILAR_TO 邊擴展概念，再找課程（折扣 HOP2_DISCOUNT）。
    回傳 (results, stats)
    """
    seed_courses = graph_service.get_course_info(course_name)
    if not seed_courses:
        return [], {}

    seed_concepts: set[str] = set()
    for sc in seed_courses:
        for tgt, rel in g["out"].get(sc["id"], []):
            if rel in ("COVERS", "TEACHES"):
                seed_concepts.add(tgt)

    if not seed_concepts:
        return [], {}

    # 2-hop 概念擴展：seed_concept → SIMILAR_TO → expanded_concept
    expanded_concepts: dict[str, float] = {}  # concept_id -> weight
    for cid in seed_concepts:
        expanded_concepts[cid] = 1.0  # 1-hop 概念，權重 1.0
    for cid in seed_concepts:
        for tgt, rel in g["out"].get(cid, []):
            if rel == "SIMILAR_TO" and tgt not in expanded_concepts:
                expanded_concepts[tgt] = HOP2_DISCOUNT
        for src, rel in g["in"].get(cid, []):  # SIMILAR_TO 是雙向的
            if rel == "SIMILAR_TO" and src not in expanded_concepts:
                expanded_concepts[src] = HOP2_DISCOUNT

    seed_ids = {sc["id"] for sc in seed_courses}
    score: dict[str, float] = {}
    hop_via: dict[str, str] = {}  # course_id -> "1hop" / "2hop" / "both"

    for concept_id, weight in expanded_concepts.items():
        is_1hop = concept_id in seed_concepts
        for src, rel in g["in"].get(concept_id, []):
            if rel in ("COVERS", "TEACHES") and src not in seed_ids:
                if g["nodes"].get(src, {}).get("node_type") == "Course":
                    score[src] = score.get(src, 0) + weight
                    hop = "1hop" if is_1hop else "2hop"
                    if src in hop_via:
                        if hop_via[src] != hop:
                            hop_via[src] = "both"
                    else:
                        hop_via[src] = hop

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:top_n]
    results = []
    for cid, s in ranked:
        n = g["nodes"].get(cid, {})
        results.append({
            "id": cid, "name": n.get("name", cid),
            "dept": n.get("dept", ""), "score": s,
            "via": hop_via.get(cid, "?"),
        })

    stats = {
        "seed_concepts": len(seed_concepts),
        "expanded_concepts": len(expanded_concepts),
        "new_concepts": len(expanded_concepts) - len(seed_concepts),
        "total_courses": len(score),
    }
    return results, stats


# ── 隨機抽樣有 concept 的課程 ─────────────────────────────────────────────────
def sample_courses_with_concepts(g: dict, n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    candidates = []
    for nid, nd in g["nodes"].items():
        if nd.get("node_type") != "Course":
            continue
        if "[已停開]" in nd.get("name", ""):
            continue
        has_concept = any(
            rel in ("COVERS", "TEACHES")
            for _, rel in g["out"].get(nid, [])
        )
        if has_concept:
            candidates.append(nd.get("name", nid))
    return rng.sample(candidates, min(n, len(candidates)))


# ── 格式化單課程比較 ──────────────────────────────────────────────────────────
def fmt_comparison(course_name: str, g: dict) -> list[str]:
    lines = [f"\n---\n", f"## {course_name}"]

    r1, seed_concepts = similar_1hop(course_name, g)
    r2, stats2        = similar_2hop(course_name, g)

    if not r1 and not r2:
        lines.append("*找不到課程或無概念節點（通識/人文課）*")
        return lines

    # 概念統計
    if stats2:
        lines.append(
            f"\n**概念節點**：{stats2['seed_concepts']} 個直接概念"
            f" + SIMILAR_TO 擴展 {stats2['new_concepts']} 個"
            f" = 共 {stats2['expanded_concepts']} 個"
        )
        lines.append(f"**候選課程池**：1-hop {len(r1)} 筆 → 2-hop {stats2['total_courses']} 筆（top {TOP_N}）")
    else:
        lines.append("*（無概念節點）*")
        return lines

    # 找出 2-hop 新增的課程
    r1_names = {r["name"] for r in r1}
    r2_only = [r for r in r2 if r["name"] not in r1_names and r["via"] == "2hop"]

    lines.append(f"\n### 1-hop vs 2-hop Top-{TOP_N} 比較\n")
    lines.append(f"| # | 2-hop 結果 | 系所 | score | via | 1-hop 排名 |")
    lines.append(f"|---|-----------|------|-------|-----|-----------|")

    r1_rank = {r["name"]: i+1 for i, r in enumerate(r1)}
    for i, r in enumerate(r2, 1):
        r1_rank_str = str(r1_rank.get(r["name"], "—（新增）"))
        lines.append(
            f"| {i} | {r['name']} | {r['dept']} | {r['score']:.2f} | {r['via']} | {r1_rank_str} |"
        )

    if r2_only:
        lines.append(f"\n**2-hop 新增課程（未出現在 1-hop top-{TOP_N}）**：{len(r2_only)} 筆")
        for r in r2_only[:5]:
            lines.append(f"  - {r['name']}（{r['dept']}，score={r['score']:.2f}）")
    else:
        lines.append(f"\n*2-hop top-{TOP_N} 與 1-hop 完全重疊，無新增*")

    return lines


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    print("載入知識圖譜...")
    g = graph_service._g()
    print(f"  節點：{len(g['nodes'])}，邊：{sum(len(v) for v in g['out'].values())}")

    # 隨機抽樣
    random_courses = sample_courses_with_concepts(g, N_RANDOM, RANDOM_SEED)
    all_courses = FIXED_COURSES + random_courses

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# 2-hop 概念擴展相似課推薦測試")
    lines.append(f"\n執行時間：{now}  ")
    lines.append(f"參數：TOP_N={TOP_N}，HOP2_DISCOUNT={HOP2_DISCOUNT}  ")
    lines.append(
        "\n**方法說明**\n"
        "- **1-hop**（現有）：Course → COVERS/TEACHES → Concept → (反向) → Course  \n"
        "- **2-hop**（新增）：延伸到 Concept → SIMILAR_TO → Concept' → Course，折扣 0.5  \n"
        "- `via=both`：課程同時被 1-hop 和 2-hop 路徑命中（加總分數更高）  \n"
        "- `via=2hop`：**僅靠 SIMILAR_TO 擴展找到的新課程**（1-hop 找不到的）\n"
    )
    lines.append(f"**測試課程**：指定 {len(FIXED_COURSES)} 門 + 隨機抽樣 {len(random_courses)} 門\n")
    lines.append(f"隨機抽到：{'、'.join(random_courses)}\n")

    for course in all_courses:
        print(f"  {course}...")
        lines.extend(fmt_comparison(course, g))

    # 整體統計
    lines.append("\n---\n\n## 整體統計：2-hop 新增課程率\n")
    lines.append("| 課程 | 1-hop 概念 | SIMILAR_TO 擴展 | 2-hop 新增 |")
    lines.append("|------|-----------|----------------|-----------|")
    for course in all_courses:
        r1, _     = similar_1hop(course, g)
        r2, stats = similar_2hop(course, g)
        if not stats:
            lines.append(f"| {course} | — | — | — |")
            continue
        r1_names = {r["name"] for r in r1}
        new = sum(1 for r in r2 if r["name"] not in r1_names and r["via"] == "2hop")
        lines.append(
            f"| {course} | {stats['seed_concepts']} | +{stats['new_concepts']} | {new} 筆新增 |"
        )

    out_dir  = ROOT / "data" / "test_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{ts}_2hop_similar.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ 輸出：{out_path}")


if __name__ == "__main__":
    main()
