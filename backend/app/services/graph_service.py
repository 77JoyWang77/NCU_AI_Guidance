"""
graph_service.py

從 knowledge_graph.json 提供結構化圖查詢。
Graph schema（實際邊 relation）：
  HAS_CURRICULUM    — Dept/CBP/Track → CurriculumPlan
  REQUIRES          — CurriculumPlan → Course（系所必修）
  HAS_ELECTIVE_GROUP — CurriculumPlan → ElectiveGroup
  OFFERS_ELECTIVE   — ElectiveGroup/Slot → Course（選修選項）
  HAS_SLOT          — ElectiveGroup → Slot
  PROGRAM_REQUIRES  — CreditProgram → Course（學程必修）
  PROGRAM_OFFERS    — CreditProgram → ElectiveGroup（學程選修群）
  REQUIRES_SLOT     — CreditProgram → Slot
  TAUGHT_BY         — Course → Instructor
  HAS_CREDIT_PROGRAM — College → CreditProgram
  REQUIRES_PROGRAM  — Dept/CBP → CreditProgram（畢業必須完成學程）
"""

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
GRAPH_JSON = ROOT / "data" / "processed" / "graph" / "knowledge_graph.json"
SCHEDULE_DIR = ROOT / "data" / "processed" / "schedule_draft"


@lru_cache(maxsize=1)
def _load_graph() -> dict:
    with open(GRAPH_JSON, encoding="utf-8") as f:
        raw = json.load(f)

    nodes: dict[str, dict] = {n["id"]: n for n in raw["nodes"]}
    edges: list[dict] = raw.get("links", raw.get("edges", []))

    # 建立出向鄰接表 {src: [(tgt, relation)]}
    out_adj: dict[str, list[tuple[str, str]]] = {nid: [] for nid in nodes}
    # 建立反向索引 {tgt: [(src, relation)]}
    in_adj: dict[str, list[tuple[str, str]]] = {nid: [] for nid in nodes}

    for e in edges:
        src, tgt, rel = e["source"], e["target"], e["relation"]
        if src in out_adj:
            out_adj[src].append((tgt, rel))
        if tgt in in_adj:
            in_adj[tgt].append((src, rel))

    return {"nodes": nodes, "edges": edges, "out": out_adj, "in": in_adj}


def _g():
    return _load_graph()


def _node(nid: str) -> dict:
    return _g()["nodes"].get(nid, {})


def _find_nodes_by(attr: str, value: str, node_type: str = None) -> list[str]:
    """找所有 attr==value 的節點 id（可加 node_type 過濾）"""
    results = []
    for nid, n in _g()["nodes"].items():
        if n.get(attr) == value:
            if node_type is None or n.get("node_type") == node_type:
                results.append(nid)
    return results


# ── 公開查詢 API ─────────────────────────────────────────────────────────────

def _find_dept_like(dept_name: str) -> list[str]:
    """找系所節點（精確 + 模糊，涵蓋 Department / DeptGroup / CollegeBachelorProgram）"""
    dept_types = {"Department", "DeptGroup", "CollegeBachelorProgram"}
    exact = [
        nid for nid, n in _g()["nodes"].items()
        if n.get("node_type") in dept_types and n.get("name") == dept_name
    ]
    if exact:
        return exact
    return [
        nid for nid, n in _g()["nodes"].items()
        if n.get("node_type") in dept_types and dept_name in n.get("name", "")
    ]


def _collect_courses_from_plan(plan_id: str, relation_label: str) -> list[dict]:
    """
    從 CurriculumPlan 出發，收集直接 REQUIRES 課程。
    relation_label：供輸出用，如「必修」「選修」。
    """
    results = []
    for tgt, rel in _g()["out"].get(plan_id, []):
        if rel == "REQUIRES":
            n = _node(tgt)
            if n.get("node_type") == "Course":
                results.append({
                    "id": tgt,
                    "name": n.get("name", tgt),
                    "credits": n.get("credits"),
                    "relation": relation_label,
                })
    return results


def _collect_electives_from_plan(plan_id: str) -> list[dict]:
    """
    從 CurriculumPlan 出發，透過 HAS_ELECTIVE_GROUP → OFFERS_ELECTIVE (+ HAS_SLOT) 收集選修課。
    """
    results = []
    for eg_id, rel1 in _g()["out"].get(plan_id, []):
        if rel1 != "HAS_ELECTIVE_GROUP":
            continue
        # 直接 OFFERS_ELECTIVE
        for c_id, rel2 in _g()["out"].get(eg_id, []):
            if rel2 == "OFFERS_ELECTIVE":
                n = _node(c_id)
                if n.get("node_type") == "Course":
                    results.append({
                        "id": c_id,
                        "name": n.get("name", c_id),
                        "credits": n.get("credits"),
                        "relation": "選修",
                    })
            elif rel2 == "HAS_SLOT":
                for c_id2, rel3 in _g()["out"].get(c_id, []):
                    if rel3 == "OFFERS_ELECTIVE":
                        n = _node(c_id2)
                        if n.get("node_type") == "Course":
                            results.append({
                                "id": c_id2,
                                "name": n.get("name", c_id2),
                                "credits": n.get("credits"),
                                "relation": "選修",
                            })
    return results


def get_dept_required_courses(dept_name: str) -> list[dict]:
    """回傳某系所的必修課程 list（兩段路：Dept → CurriculumPlan → Course）"""
    dept_ids = _find_dept_like(dept_name)
    results = []
    seen: set[str] = set()
    for did in dept_ids:
        for plan_id, rel in _g()["out"].get(did, []):
            if rel == "HAS_CURRICULUM":
                for course in _collect_courses_from_plan(plan_id, "必修"):
                    if course["id"] not in seen:
                        seen.add(course["id"])
                        results.append(course)
    return results


def get_dept_elective_courses(dept_name: str) -> list[dict]:
    """回傳某系所的選修課程 list"""
    dept_ids = _find_dept_like(dept_name)
    results = []
    seen: set[str] = set()
    for did in dept_ids:
        for plan_id, rel in _g()["out"].get(did, []):
            if rel == "HAS_CURRICULUM":
                for course in _collect_electives_from_plan(plan_id):
                    if course["id"] not in seen:
                        seen.add(course["id"])
                        results.append(course)
    return results


def get_program_courses(program_name: str) -> list[dict]:
    """回傳學分學程的必/選修課程"""
    prog_ids = _find_nodes_by("name", program_name, "CreditProgram")
    if not prog_ids:
        prog_ids = [
            nid for nid, n in _g()["nodes"].items()
            if n.get("node_type") == "CreditProgram" and program_name in n.get("name", "")
        ]
    results = []
    seen: set[str] = set()
    for pid in prog_ids:
        for tgt, rel in _g()["out"].get(pid, []):
            if rel == "PROGRAM_REQUIRES":
                n = _node(tgt)
                if n.get("node_type") == "Course" and tgt not in seen:
                    seen.add(tgt)
                    results.append({
                        "id": tgt,
                        "name": n.get("name", tgt),
                        "credits": n.get("credits"),
                        "relation": "學程必修",
                    })
            elif rel == "PROGRAM_OFFERS":
                # ElectiveGroup → OFFERS_ELECTIVE
                for c_id, rel2 in _g()["out"].get(tgt, []):
                    if rel2 == "OFFERS_ELECTIVE":
                        n = _node(c_id)
                        if n.get("node_type") == "Course" and c_id not in seen:
                            seen.add(c_id)
                            results.append({
                                "id": c_id,
                                "name": n.get("name", c_id),
                                "credits": n.get("credits"),
                                "relation": "學程選修",
                            })
                    elif rel2 == "HAS_SLOT":
                        for c_id2, rel3 in _g()["out"].get(c_id, []):
                            if rel3 == "OFFERS_ELECTIVE":
                                n = _node(c_id2)
                                if n.get("node_type") == "Course" and c_id2 not in seen:
                                    seen.add(c_id2)
                                    results.append({
                                        "id": c_id2,
                                        "name": n.get("name", c_id2),
                                        "credits": n.get("credits"),
                                        "relation": "學程選修",
                                    })
            elif rel == "REQUIRES_SLOT":
                # Slot → OFFERS_ELECTIVE
                for c_id, rel2 in _g()["out"].get(tgt, []):
                    if rel2 == "OFFERS_ELECTIVE":
                        n = _node(c_id)
                        if n.get("node_type") == "Course" and c_id not in seen:
                            seen.add(c_id)
                            results.append({
                                "id": c_id,
                                "name": n.get("name", c_id),
                                "credits": n.get("credits"),
                                "relation": "學程必修（擇一）",
                            })
    return results


def get_teacher_courses(teacher_name: str) -> list[dict]:
    """回傳某教師所授的課程。

    查詢路徑（優先順序）：
    1. Course --[TAUGHT_BY]--> Instructor（走反向邊）
    2. Instructor --[COURSE_EXPERT]--> Course（NLP 分析的專長關聯課程，作為補充）
    """
    teacher_ids = _find_nodes_by("name", teacher_name, "Instructor")
    if not teacher_ids:
        teacher_ids = [
            nid for nid, n in _g()["nodes"].items()
            if n.get("node_type") == "Instructor" and teacher_name in n.get("name", "")
        ]
    results = []
    seen: set[str] = set()

    for tid in teacher_ids:
        # 路徑 1：TAUGHT_BY 反向邊（實際授課紀錄）
        for src, rel in _g()["in"].get(tid, []):
            if rel == "TAUGHT_BY" and src not in seen:
                seen.add(src)
                course_node = _node(src)
                results.append({
                    "id": src,
                    "name": course_node.get("name", src),
                    "credits": course_node.get("credits"),
                    "relation": "授課",
                })

    # 路徑 2：COURSE_EXPERT 出向邊（當 TAUGHT_BY 結果為空時，補充專長關聯）
    if not results:
        for tid in teacher_ids:
            for tgt, rel in _g()["out"].get(tid, []):
                if rel == "COURSE_EXPERT" and tgt not in seen:
                    seen.add(tgt)
                    course_node = _node(tgt)
                    if course_node.get("node_type") == "Course":
                        results.append({
                            "id": tgt,
                            "name": course_node.get("name", tgt),
                            "credits": course_node.get("credits"),
                            "relation": "專長相關",
                        })

    return results


def get_course_info(course_name_or_code: str) -> list[dict]:
    """用名稱（雙向模糊比對）或代碼查課程節點基本資訊"""
    results = []
    for nid, n in _g()["nodes"].items():
        if n.get("node_type") != "Course":
            continue
        name = n.get("name", "")
        code = n.get("code", "")
        if course_name_or_code == code:
            results.append({"id": nid, **n})
            continue
        # 雙向包含比對（排除空名稱）：query 包含課名 或 課名包含 query
        if name and (course_name_or_code in name or name in course_name_or_code):
            results.append({"id": nid, **n})
    return results


def search_courses_by_concept_cluster(seed_course_name: str, top_n: int = 20) -> list[dict]:
    """
    給定課程名稱，透過共享 Concept/Technology 節點找最相似的跨系課程。

    步驟：
    1. 找 seed 課程的 COVERS / TEACHES 出向邊 → Concept/Technology 節點集合
    2. 走反向邊找到有共同 Concept 的其他課程
    3. 以共同 Concept 數量排序，回傳 top_n
    """
    seed_courses = get_course_info(seed_course_name)
    if not seed_courses:
        return []

    seed_concepts: set[str] = set()
    for sc in seed_courses:
        for tgt, rel in _g()["out"].get(sc["id"], []):
            if rel in ("COVERS", "TEACHES"):
                seed_concepts.add(tgt)

    if not seed_concepts:
        return []

    seed_ids = {sc["id"] for sc in seed_courses}
    score: dict[str, int] = {}
    for concept_id in seed_concepts:
        for src, rel in _g()["in"].get(concept_id, []):
            if rel in ("COVERS", "TEACHES") and src not in seed_ids:
                if _node(src).get("node_type") == "Course":
                    score[src] = score.get(src, 0) + 1

    ranked = sorted(score.items(), key=lambda x: x[1], reverse=True)[:top_n]
    results = []
    for cid, cnt in ranked:
        n = _node(cid)
        results.append({
            "id":             cid,
            "name":           n.get("name", cid),
            "dept":           n.get("dept", ""),
            "credits":        n.get("credits"),
            "level":          n.get("level", ""),
            "shared_concepts": cnt,
        })
    return results


def search_courses_by_tech(tech_name: str) -> list[dict]:
    """
    Graph-first 技術查課：
    走 tech::{name} / concept::{name} 節點的反向邊（TEACHES / COVERS）找到所有課程。
    比向量搜尋更精確，不漏課。
    """
    results = []
    seen: set[str] = set()

    # 精確 id 查找
    candidate_ids = [
        f"tech::{tech_name}",
        f"concept::{tech_name}",
        f"field::{tech_name}",
    ]
    # 也做模糊比對（大小寫不同、簡稱等）
    lower = tech_name.lower()
    for nid, n in _g()["nodes"].items():
        if n.get("node_type") in ("Technology", "Concept", "Field"):
            if n.get("name", "").lower() == lower:
                candidate_ids.append(nid)

    # 去重
    candidate_ids = list(dict.fromkeys(candidate_ids))

    for tech_nid in candidate_ids:
        if not _g()["nodes"].get(tech_nid):
            continue
        for src, rel in _g()["in"].get(tech_nid, []):
            if rel in ("TEACHES", "COVERS", "COVERS_FIELD") and src not in seen:
                course_node = _node(src)
                if course_node.get("node_type") == "Course":
                    seen.add(src)
                    results.append({
                        "id": src,
                        "name": course_node.get("name", src),
                        "credits": course_node.get("credits"),
                        "dept": course_node.get("dept", ""),
                        "level": course_node.get("level", ""),
                        "tech_node": tech_nid,
                    })

    return results


def list_all_programs() -> list[dict]:
    """列出所有學分學程"""
    return [
        {"id": nid, "name": n.get("name", ""), "college": n.get("college", "")}
        for nid, n in _g()["nodes"].items()
        if n.get("node_type") == "CreditProgram"
    ]


def get_graduation_rules(dept_name: str) -> dict:
    """從 schedule_draft 取得系所畢業規定（模糊名稱比對）"""
    if not SCHEDULE_DIR.exists():
        return {}
    for college_dir in SCHEDULE_DIR.iterdir():
        if not college_dir.is_dir():
            continue
        for fp in college_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if dept_name in data.get("name", ""):
                    return {
                        "dept_name": data.get("name", ""),
                        "min_credits": data.get("min_credits", 0),
                        "required_credits": data.get("required_credits", 0),
                        "graduation_rules": data.get("graduation_rules", []),
                        "certifications": data.get("certifications", []),
                    }
            except Exception:
                pass
    return {}


def get_course_knowledge_map(course_name: str) -> dict:
    """
    回傳一門課的知識地圖：它在學什麼、使用什麼技術，以及概念重疊最多的跨系相似課程。

    回傳格式：
    {
      "course": {id, name, dept, credits},
      "concepts": [{name, node_type}],
      "technologies": [{name}],
      "similar_courses": [{name, dept, credits, shared_concepts}],
    }
    """
    courses = get_course_info(course_name)
    if not courses:
        return {}

    # 聚合多個同名課程的概念（如演算法有多個系開課）
    all_concept_ids: set[str] = set()
    all_tech_ids: set[str] = set()
    for sc in courses:
        for tgt, rel in _g()["out"].get(sc["id"], []):
            if rel == "COVERS":
                all_concept_ids.add(tgt)
            elif rel == "TEACHES":
                all_tech_ids.add(tgt)

    concepts = []
    for cid in all_concept_ids:
        n = _node(cid)
        concepts.append({"name": n.get("name", cid), "node_type": n.get("node_type", "")})

    technologies = []
    for tid in all_tech_ids:
        n = _node(tid)
        technologies.append({"name": n.get("name", tid)})

    similar = search_courses_by_concept_cluster(course_name, top_n=10)

    primary = courses[0]
    return {
        "course": {
            "id":      primary["id"],
            "name":    primary.get("name", ""),
            "dept":    primary.get("dept", ""),
            "credits": primary.get("credits"),
        },
        "concepts":        sorted(concepts, key=lambda x: x["name"]),
        "technologies":    technologies,
        "similar_courses": similar,
    }


def get_depts_by_tech(tech_name: str) -> dict:
    """
    Multi-hop 查詢：哪些系所的課程有教某技術/概念？
    區分「必修課含此技術」與「選修課含此技術」。

    路徑：
      tech/concept 節點 → 反向 TEACHES/COVERS → Course
      Course → 反向 REQUIRES ← CurriculumPlan → 反向 HAS_CURRICULUM ← Department
    """
    # 1. 找技術 / 概念節點
    candidate_node_ids: list[str] = [
        f"tech::{tech_name}", f"concept::{tech_name}", f"field::{tech_name}",
    ]
    lower = tech_name.lower()
    for nid, n in _g()["nodes"].items():
        if n.get("node_type") in ("Technology", "Concept", "Field"):
            if n.get("name", "").lower() == lower:
                candidate_node_ids.append(nid)
    candidate_node_ids = list(dict.fromkeys(candidate_node_ids))

    # 2. 找到所有教此技術的 Course 節點
    tech_courses: set[str] = set()
    for tech_nid in candidate_node_ids:
        if not _g()["nodes"].get(tech_nid):
            continue
        for src, rel in _g()["in"].get(tech_nid, []):
            if rel in ("TEACHES", "COVERS", "COVERS_FIELD"):
                if _node(src).get("node_type") == "Course":
                    tech_courses.add(src)

    if not tech_courses:
        return {"tech": tech_name, "required_depts": [], "elective_depts": [], "courses": []}

    # 3. 對每門課追溯回系所，區分必修/選修
    required_depts: dict[str, str] = {}   # dept_name → dept_id
    elective_depts: dict[str, str] = {}
    course_list = []

    dept_types = {"Department", "DeptGroup", "CollegeBachelorProgram"}

    for course_id in tech_courses:
        cn = _node(course_id)
        course_list.append({
            "id":   course_id,
            "name": cn.get("name", course_id),
            "dept": cn.get("dept", ""),
        })

        # 反向追溯：REQUIRES / OFFERS_ELECTIVE ← CurriculumPlan ← HAS_CURRICULUM ← Dept
        for plan_id, rel in _g()["in"].get(course_id, []):
            plan_node = _node(plan_id)
            if plan_node.get("node_type") != "CurriculumPlan":
                continue
            is_required = (rel == "REQUIRES")
            for dept_id, rel2 in _g()["in"].get(plan_id, []):
                if rel2 == "HAS_CURRICULUM":
                    dept_node = _node(dept_id)
                    if dept_node.get("node_type") in dept_types:
                        name = dept_node.get("name", dept_id)
                        if is_required:
                            required_depts[name] = dept_id
                        else:
                            elective_depts[name] = dept_id

    # 從 course metadata 補充（課程 dept 欄位）
    all_known_dept_names = set(required_depts) | set(elective_depts)
    for c in course_list:
        if c["dept"] and c["dept"] not in all_known_dept_names:
            elective_depts[c["dept"]] = c["dept"]

    return {
        "tech":          tech_name,
        "required_depts": sorted(required_depts.keys()),
        "elective_depts": sorted(elective_depts.keys()),
        "courses":        course_list[:30],
    }


def ppr_explore(
    seed_names: list[str],
    top_k: int = 20,
    alpha: float = 0.85,
    n_iter: int = 25,
    node_type_filter: list[str] = None,
) -> list[dict]:
    """
    Personalized PageRank 探索：從種子節點出發，在圖上做帶重置的隨機遊走，
    回傳與種子最相關的 top_k 節點（跨節點類型）。

    比 concept cluster 更能做到多跳、跨類型的語意擴散。
    SIMILAR_TO 邊建立後，同義概念會自然獲得高分。

    seed_names:        概念/技術/課程名稱列表
    alpha:             延續前進的機率（1-alpha = 重置到種子的機率）
    node_type_filter:  若指定，只回傳特定類型的節點（如 ["Course", "Instructor"]）
    """
    g = _g()

    # 找種子節點：只從語意節點中找，且只做 query→name 方向的包含比對
    _SEED_TYPES = {"Concept", "Technology", "Field", "Course"}
    seed_ids: set[str] = set()
    for name in seed_names:
        nl = name.lower()
        for nid, nd in g["nodes"].items():
            if nd.get("node_type") not in _SEED_TYPES:
                continue
            nname = nd.get("name", "").lower()
            if not nname:
                continue
            # 精確 or query 包含在節點名稱中（不反向，避免「機器」「學習」等片段成為種子）
            if nl == nname or nl in nname:
                seed_ids.add(nid)

    if not seed_ids:
        return []

    n_seeds = len(seed_ids)
    restart_each = (1.0 - alpha) / n_seeds

    # 初始化分數
    scores: dict[str, float] = {nid: 1.0 / n_seeds for nid in seed_ids}

    # Power iteration（undirected：同時用 out_adj 和 in_adj）
    for _ in range(n_iter):
        new_s: dict[str, float] = {}
        for src, score in scores.items():
            nbrs: list[str] = []
            for tgt, _ in g["out"].get(src, []):
                nbrs.append(tgt)
            for orig, _ in g["in"].get(src, []):
                nbrs.append(orig)
            if not nbrs:
                continue
            spread = alpha * score / len(nbrs)
            for nb in nbrs:
                new_s[nb] = new_s.get(nb, 0.0) + spread
        # Restart
        for nid in seed_ids:
            new_s[nid] = new_s.get(nid, 0.0) + restart_each
        scores = new_s

    # 正規化
    total = sum(scores.values()) or 1.0
    scores = {k: v / total for k, v in scores.items()}

    allowed = set(node_type_filter) if node_type_filter else None
    results: list[dict] = []

    for nid, score in sorted(scores.items(), key=lambda x: -x[1]):
        if nid in seed_ids:
            continue
        nd = g["nodes"].get(nid, {})
        ntype = nd.get("node_type", "")
        if allowed and ntype not in allowed:
            continue
        results.append({
            "id":        nid,
            "name":      nd.get("name", nid),
            "node_type": ntype,
            "dept":      nd.get("dept", ""),
            "credits":   nd.get("credits"),
            "score":     round(score * 1000, 4),  # 乘 1000 讓數字可讀
        })
        if len(results) >= top_k:
            break

    return results


def list_all_departments() -> list[dict]:
    """列出所有系所"""
    return [
        {"id": nid, "name": n.get("name", ""), "college": n.get("college", "")}
        for nid, n in _g()["nodes"].items()
        if n.get("node_type") in ("Department", "DeptGroup", "CollegeBachelorProgram")
    ]
