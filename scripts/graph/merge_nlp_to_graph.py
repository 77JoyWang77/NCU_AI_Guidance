"""
merge_nlp_to_graph.py

將 NLP Pipeline 的輸出整合進現有知識圖譜（knowledge_graph.gpickle）。

新增節點類型：
  Field：學術研究領域（來自教師專長，細粒度）

新增邊類型：
  COVERS_FIELD   Course → Field  （課程涵蓋此學術領域，帶 relevance 屬性）
  RELEVANT_EXPERT Instructor → Field  （教師是此領域的研究專家）
  TAGGED_AS      Course → Topic  （通識課程主題分類，reuse Domain 節點）

輸入：
  data/processed/graph/knowledge_graph.gpickle
  data/processed/nlp_domain_tags.json
  data/processed/nlp_professor_links.json
  data/processed/nlp_topic_tags.json
  data/processed/dept_professor_map.json

輸出：
  data/processed/graph/knowledge_graph.gpickle  （更新）
  data/processed/graph/knowledge_graph.json     （更新）
  data/processed/graph/knowledge_graph_stats.json（更新）
"""

import json
import pickle
import re
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    print("請先安裝 networkx：pip install networkx")
    raise

BASE         = Path(__file__).parent.parent.parent
GRAPH_PKL    = BASE / "data" / "processed" / "graph" / "knowledge_graph.gpickle"
GRAPH_JSON   = BASE / "data" / "processed" / "graph" / "knowledge_graph.json"
GRAPH_STATS  = BASE / "data" / "processed" / "graph" / "knowledge_graph_stats.json"

DOMAIN_TAGS_PATH  = BASE / "data" / "processed" / "nlp_domain_tags.json"
PROF_LINKS_PATH   = BASE / "data" / "processed" / "nlp_professor_links.json"
TOPIC_TAGS_PATH   = BASE / "data" / "processed" / "nlp_topic_tags.json"
DEPT_MAP_PATH     = BASE / "data" / "processed" / "dept_professor_map.json"


def load_graph() -> nx.DiGraph:
    with open(GRAPH_PKL, "rb") as f:
        return pickle.load(f)


def save_graph(G: nx.DiGraph):
    with open(GRAPH_PKL, "wb") as f:
        pickle.dump(G, f)

    # 匯出 JSON（adjacency 格式）
    data = nx.readwrite.json_graph.node_link_data(G)
    with open(GRAPH_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_field_nodes_and_edges(G: nx.DiGraph, domain_tags: dict, dept_map: dict):
    """
    1. 新增 Field 節點（來自教師專長）
    2. 新增 COVERS_FIELD 邊（Course → Field）
    3. 新增 RELEVANT_EXPERT 邊（Instructor → Field）
    """
    added_fields = 0
    added_covers = 0
    added_experts = 0

    # 先收集所有 Field，一次建好節點
    all_fields: set[str] = set()
    for code_data in domain_tags.values():
        for tag in code_data.get("domain_tags", []):
            field = tag.get("field", "").strip()
            if field:
                all_fields.add(field)

    for field in all_fields:
        fid = f"field::{field}"
        if not G.has_node(fid):
            G.add_node(fid, node_type="Field", name=field, source="teacher_specialty")
            added_fields += 1

    # COVERS_FIELD：Course → Field
    for course_code, data in domain_tags.items():
        if data.get("skipped"):
            continue
        # 嘗試在圖中找到課程節點（course_code 可能有不同格式）
        if not G.has_node(course_code):
            continue
        for tag in data.get("domain_tags", []):
            field = tag.get("field", "").strip()
            if not field:
                continue
            fid = f"field::{field}"
            if not G.has_node(fid):
                continue
            G.add_edge(
                course_code, fid,
                relation="COVERS_FIELD",
                relevance=tag.get("relevance", "medium"),
                source="llm_agent2",
            )
            added_covers += 1

    # RELEVANT_EXPERT：Instructor → Field（從 dept_professor_map 建立）
    for dept, dept_data in dept_map.items():
        for prof in dept_data.get("professors", []):
            iid = f"instructor::{prof['name']}"
            if not G.has_node(iid):
                continue
            for spec in prof.get("specialties", []):
                fid = f"field::{spec}"
                if not G.has_node(fid):
                    continue
                if not G.has_edge(iid, fid):
                    G.add_edge(
                        iid, fid,
                        relation="RELEVANT_EXPERT",
                        dept=dept,
                    )
                    added_experts += 1

    print(f"  新增 Field 節點：{added_fields}")
    print(f"  新增 COVERS_FIELD 邊：{added_covers}")
    print(f"  新增 RELEVANT_EXPERT 邊：{added_experts}")
    return added_fields, added_covers, added_experts


def add_topic_tags(G: nx.DiGraph, topic_tags: dict):
    """
    通識課程：
    1. 新增 TAGGED_AS 邊（Course → Domain，reuse 現有 Domain 節點或新建）
    2. 將 core_questions 存為課程節點屬性
    """
    # 可選主題標籤 → Domain 節點 ID 對照
    # 若圖中已有同名 Domain 節點就 reuse，否則新建
    TOPIC_LABELS = [
        "哲學", "歷史", "文學", "語言學", "藝術", "音樂",
        "社會學", "心理學", "法律", "政治", "經濟",
        "物理", "化學", "生物", "環境科學", "數學",
        "資訊科技", "工程", "醫學",
        "倫理學", "性別研究", "族群文化", "全球化", "永續發展",
    ]

    # 預先確保 Domain 節點存在
    topic_node_map: dict[str, str] = {}
    for label in TOPIC_LABELS:
        # 找圖中是否有同名 Domain 節點
        found = None
        for nid, attrs in G.nodes(data=True):
            if attrs.get("node_type") == "Domain" and attrs.get("name") == label:
                found = nid
                break
        if found:
            topic_node_map[label] = found
        else:
            nid = f"domain::topic::{label}"
            if not G.has_node(nid):
                G.add_node(nid, node_type="Domain", name=label, source="topic_classification")
            topic_node_map[label] = nid

    added_tagged = 0
    updated_props = 0

    for course_code, data in topic_tags.items():
        if data.get("skipped"):
            continue
        if not G.has_node(course_code):
            continue

        # core_questions 存為節點屬性
        cqs = data.get("core_questions", [])
        if cqs:
            G.nodes[course_code]["core_questions"] = cqs
            updated_props += 1

        # TAGGED_AS 邊
        for tag in data.get("topic_tags", []):
            if tag in topic_node_map:
                G.add_edge(
                    course_code, topic_node_map[tag],
                    relation="TAGGED_AS",
                    source="llm_agent3",
                )
                added_tagged += 1

    print(f"  新增 TAGGED_AS 邊（通識）：{added_tagged}")
    print(f"  更新 core_questions 屬性：{updated_props} 門課")
    return added_tagged, updated_props


def compute_stats(G: nx.DiGraph) -> dict:
    node_types: dict[str, int] = {}
    edge_types: dict[str, int] = {}

    for _, attrs in G.nodes(data=True):
        t = attrs.get("node_type", "Unknown")
        node_types[t] = node_types.get(t, 0) + 1

    for _, _, attrs in G.edges(data=True):
        r = attrs.get("relation", "Unknown")
        edge_types[r] = edge_types.get(r, 0) + 1

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": dict(sorted(node_types.items(), key=lambda x: -x[1])),
        "edge_types": dict(sorted(edge_types.items(), key=lambda x: -x[1])),
    }


def main():
    print("=== merge_nlp_to_graph.py ===")

    if not GRAPH_PKL.exists():
        print(f"找不到圖譜：{GRAPH_PKL}")
        print("請先執行 build_knowledge_graph.py")
        return

    G = load_graph()
    print(f"載入圖譜：{G.number_of_nodes()} 節點，{G.number_of_edges()} 邊")

    # 載入 NLP 輸出
    domain_tags = {}
    if DOMAIN_TAGS_PATH.exists():
        with open(DOMAIN_TAGS_PATH, encoding="utf-8") as f:
            domain_tags = json.load(f)
        print(f"載入 nlp_domain_tags：{len(domain_tags)} 筆")
    else:
        print("找不到 nlp_domain_tags.json，跳過 COVERS_FIELD")

    prof_links = {}
    if PROF_LINKS_PATH.exists():
        with open(PROF_LINKS_PATH, encoding="utf-8") as f:
            prof_links = json.load(f)
        print(f"載入 nlp_professor_links：{len(prof_links)} 門課")

    dept_map = {}
    if DEPT_MAP_PATH.exists():
        with open(DEPT_MAP_PATH, encoding="utf-8") as f:
            dept_map = json.load(f)
        print(f"載入 dept_professor_map：{len(dept_map)} 個系所")

    topic_tags = {}
    if TOPIC_TAGS_PATH.exists():
        with open(TOPIC_TAGS_PATH, encoding="utf-8") as f:
            topic_tags = json.load(f)
        print(f"載入 nlp_topic_tags：{len(topic_tags)} 筆")
    else:
        print("找不到 nlp_topic_tags.json，跳過通識主題")

    # 注入圖譜
    if domain_tags or dept_map:
        print("\n注入 Field 節點與 COVERS_FIELD / RELEVANT_EXPERT 邊...")
        add_field_nodes_and_edges(G, domain_tags, dept_map)

    if topic_tags:
        print("\n注入通識主題標籤...")
        add_topic_tags(G, topic_tags)

    # 存檔
    print("\n存檔中...")
    save_graph(G)

    stats = compute_stats(G)
    with open(GRAPH_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n完成！圖譜現在有 {stats['total_nodes']} 節點，{stats['total_edges']} 邊")
    print(f"輸出：{GRAPH_PKL}")
    print(f"輸出：{GRAPH_JSON}")


if __name__ == "__main__":
    main()
