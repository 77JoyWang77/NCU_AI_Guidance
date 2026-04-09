from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import json
from pathlib import Path

router = APIRouter()

GRAPH_JSON_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "data" / "processed" / "graph" / "knowledge_graph.json"
)

# Module-level cache (loaded once on first request)
_graph_cache: dict | None = None


def _load_graph() -> dict:
    global _graph_cache
    if _graph_cache is not None:
        return _graph_cache

    with open(GRAPH_JSON_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    nodes: dict[str, dict] = {n["id"]: n for n in raw["nodes"]}
    edges: list[dict] = raw.get("links", raw.get("edges", []))

    # Build bidirectional adjacency list
    adj: dict[str, list[dict]] = {nid: [] for nid in nodes}
    for e in edges:
        src, tgt, rel = e["source"], e["target"], e["relation"]
        if src in adj:
            adj[src].append({"neighbor": tgt, "relation": rel, "direction": "out"})
        if tgt in adj:
            adj[tgt].append({"neighbor": src, "relation": rel, "direction": "in"})

    _graph_cache = {"nodes": nodes, "adj": adj, "edges": edges}
    return _graph_cache


# ─────────────────────────────────────────────
# GET /api/graph/search?q=xxx&types=xxx&limit=20
# ─────────────────────────────────────────────
@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=1),
    types: Optional[str] = Query(None, description="逗號分隔的節點類型白名單"),
    limit: int = Query(20, ge=1, le=100),
):
    g = _load_graph()
    nodes = g["nodes"]
    q_lower = q.lower()
    type_filter = set(types.split(",")) if types else None

    results = []
    for nid, n in nodes.items():
        if type_filter and n.get("node_type") not in type_filter:
            continue
        name = n.get("name", "")
        if q_lower in name.lower() or q_lower in nid.lower():
            results.append(n)
        if len(results) >= limit:
            break

    return results


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/graph/neighborhood?node_id=xxx&depth=1&max_nodes=80
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/neighborhood")
async def get_neighborhood(
    node_id: str = Query(...),
    depth: int = Query(1, ge=1, le=3),
    max_nodes: int = Query(80, ge=1, le=200),
):
    g = _load_graph()
    nodes = g["nodes"]
    adj = g["adj"]
    all_edges = g["edges"]

    if node_id not in nodes:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    # BFS
    visited: set[str] = {node_id}
    queue: list[tuple[str, int]] = [(node_id, 0)]
    head = 0

    while head < len(queue):
        current, d = queue[head]
        head += 1
        if d >= depth:
            continue
        for conn in adj.get(current, []):
            nbr = conn["neighbor"]
            if nbr not in visited and nbr in nodes:
                visited.add(nbr)
                queue.append((nbr, d + 1))
                if len(visited) >= max_nodes:
                    break
        if len(visited) >= max_nodes:
            break

    result_nodes = [nodes[nid] for nid in visited]
    result_edges = [
        e for e in all_edges
        if e["source"] in visited and e["target"] in visited
    ]

    return {"nodes": result_nodes, "edges": result_edges}


# ─────────────────────────────────────────────────────────────
# GET /api/graph/stats  —  基本統計（供頁面初次載入顯示）
# ─────────────────────────────────────────────────────────────
@router.get("/stats")
async def get_stats():
    g = _load_graph()
    from collections import Counter
    type_counts = Counter(n.get("node_type", "?") for n in g["nodes"].values())
    rel_counts = Counter(e.get("relation", "?") for e in g["edges"])
    return {
        "total_nodes": len(g["nodes"]),
        "total_edges": len(g["edges"]),
        "node_types": dict(type_counts.most_common()),
        "relation_types": dict(rel_counts.most_common()),
    }
