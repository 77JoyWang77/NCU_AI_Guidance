"""
compute_communities.py — 離線計算 Leiden 社群分群

在 Course + Concept + Technology 子圖上執行 Leiden 演算法，
將結果存入 data/processed/graph/communities.json。

用法：
  python scripts/graph/compute_communities.py
  python scripts/graph/compute_communities.py --min-size 3   # 社群最小課程數

前置條件：
  pip install python-igraph leidenalg
  已存在 data/processed/graph/knowledge_graph.igraph（執行 build_graph.py 生成）
  或   data/processed/graph/knowledge_graph.json
"""

import argparse
import json
from pathlib import Path

ROOT        = Path(__file__).parent.parent.parent
GRAPH_IGRAPH = ROOT / "data" / "processed" / "graph" / "knowledge_graph.pkl"
GRAPH_JSON   = ROOT / "data" / "processed" / "graph" / "knowledge_graph.json"
OUTPUT_PATH  = ROOT / "data" / "processed" / "graph" / "communities.json"

# 只保留語意邊跑 Leiden（避免行政結構邊污染社群）
SEMANTIC_RELS = {"COVERS", "TEACHES", "COVERS_FIELD", "SIMILAR_TO"}
# 只保留這些節點類型
SEMANTIC_TYPES = {"Course", "Concept", "Technology"}


def load_igraph():
    try:
        import igraph as ig
    except ImportError:
        raise ImportError("請先安裝：pip install python-igraph leidenalg")

    if GRAPH_IGRAPH.exists():
        print(f"載入 igraph 快取：{GRAPH_IGRAPH}")
        return ig.Graph.Read_Pickle(str(GRAPH_IGRAPH))

    # Fallback：從 JSON 重建
    print(f"igraph 檔案不存在，從 JSON 重建：{GRAPH_JSON}")
    raw = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    node_list = raw["nodes"]
    edge_list  = raw.get("links", raw.get("edges", []))

    id_to_idx = {n["id"]: i for i, n in enumerate(node_list)}
    G = ig.Graph(directed=True)
    G.add_vertices(len(node_list))
    for i, n in enumerate(node_list):
        G.vs[i]["name"]      = n["id"]
        G.vs[i]["node_type"] = n.get("node_type", "")
        G.vs[i]["node_name"] = n.get("name", "")
    edge_tuples, weights = [], []
    seen_similar: set = set()
    COVERS_FIELD_W = {"high": 1.5, "medium": 1.0, "low": 0.5}
    REL_WEIGHT = {"COVERS": 1.0, "TEACHES": 1.2, "COVERS_FIELD": 1.0, "SIMILAR_TO": 0.8}
    for e in edge_list:
        si = id_to_idx.get(e["source"])
        ti = id_to_idx.get(e["target"])
        if si is None or ti is None:
            continue
        rel = e.get("relation", "")
        if rel == "SIMILAR_TO":
            pair = (min(si, ti), max(si, ti))
            if pair in seen_similar:
                continue
            seen_similar.add(pair)
        w = REL_WEIGHT.get(rel, 0.3)
        if rel == "COVERS_FIELD":
            w = COVERS_FIELD_W.get(e.get("relevance", "medium"), 1.0)
        edge_tuples.append((si, ti))
        weights.append(w)
    G.add_edges(edge_tuples)
    G.es["weight"] = weights
    return G


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-size", type=int, default=3, help="社群最小課程數")
    args = parser.parse_args()

    try:
        import igraph as ig
        import leidenalg
    except ImportError as e:
        print(f"缺少依賴：{e}\n請執行：pip install python-igraph leidenalg")
        return

    G = load_igraph()
    print(f"完整圖：{G.vcount()} 節點，{G.ecount()} 邊")

    # ── Step 1：取出語意子圖（Course + Concept + Technology） ──────────────
    keep_v = [v.index for v in G.vs if v["node_type"] in SEMANTIC_TYPES]
    G_sub  = G.induced_subgraph(keep_v)
    print(f"語意子圖（節點篩選後）：{G_sub.vcount()} 節點")

    # 只保留語意邊
    keep_e = [
        e.index for e in G_sub.es
        if G_sub.vs[e.source]["node_type"] in SEMANTIC_TYPES
        and G_sub.vs[e.target]["node_type"] in SEMANTIC_TYPES
    ]
    G_sem = G_sub.subgraph_edges(keep_e, delete_vertices=False)
    print(f"語意子圖（邊篩選後）：{G_sem.vcount()} 節點，{G_sem.ecount()} 邊")

    # 轉為無向圖（Leiden 需要無向）
    G_und = G_sem.as_undirected(combine_edges={"weight": "max"})
    # 移除孤立節點（無語意邊連接）
    connected_v = [v.index for v in G_und.vs if G_und.degree(v.index) > 0]
    G_conn = G_und.induced_subgraph(connected_v)
    print(f"移除孤立節點後：{G_conn.vcount()} 節點，{G_conn.ecount()} 邊")

    # ── Step 2：執行 Leiden ──────────────────────────────────────────────────
    print("\n執行 Leiden 社群分群（加權 ModularityVertexPartition）...")
    partition = leidenalg.find_partition(
        G_conn,
        leidenalg.ModularityVertexPartition,
        weights=G_conn.es["weight"],
        n_iterations=10,
        seed=42,
    )
    print(f"找到 {len(partition)} 個社群，modularity = {partition.quality():.4f}")

    # ── Step 3：整理輸出 ─────────────────────────────────────────────────────
    communities = []
    for cid, members in enumerate(partition):
        # 用 (course_code, display_name) 去重（同課號只保留一筆）
        seen_codes: set[str] = set()
        course_entries: list[dict] = []
        for v in members:
            vx = G_conn.vs[v]
            if vx["node_type"] != "Course":
                continue
            code = vx["name"]       # node ID，即課號
            name = vx["node_name"]  # 顯示名稱
            if not name or code in seen_codes:
                continue
            seen_codes.add(code)
            course_entries.append({"code": code, "name": name})

        concepts = sorted({
            G_conn.vs[v]["node_name"] for v in members
            if G_conn.vs[v]["node_type"] in ("Concept", "Technology")
            and G_conn.vs[v]["node_name"]
        })

        if len(course_entries) < args.min_size:
            continue

        communities.append({
            "id":           cid,
            "label":        "",
            "size":         len(course_entries),
            "courses":      sorted(course_entries, key=lambda x: x["name"])[:20],
            "top_concepts": concepts[:10],
        })

    # 依社群大小降序排列
    communities.sort(key=lambda x: -x["size"])

    # ── Step 4：儲存 ─────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(communities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n儲存 {len(communities)} 個社群（≥{args.min_size} 門課）→ {OUTPUT_PATH}")

    # 顯示前 5 個社群摘要
    print("\n── 前 5 大社群預覽 ──────────────────────────────────")
    for c in communities[:5]:
        course_names = [x["name"] for x in c["courses"][:4]]
        print(f"  社群 {c['id']:3d}：{c['size']:3d} 門課  "
              f"代表概念：{', '.join(c['top_concepts'][:4])}")
        print(f"           代表課程：{', '.join(course_names)}")


if __name__ == "__main__":
    main()
