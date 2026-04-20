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
    """用名稱或代碼查課程節點基本資訊"""
    results = []
    for nid, n in _g()["nodes"].items():
        if n.get("node_type") != "Course":
            continue
        if (course_name_or_code in n.get("name", "") or
                course_name_or_code == n.get("code", "")):
            results.append({"id": nid, **n})
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


def list_all_departments() -> list[dict]:
    """列出所有系所"""
    return [
        {"id": nid, "name": n.get("name", ""), "college": n.get("college", "")}
        for nid, n in _g()["nodes"].items()
        if n.get("node_type") in ("Department", "DeptGroup", "CollegeBachelorProgram")
    ]
