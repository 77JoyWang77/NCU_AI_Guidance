"""
curriculum.py — 修課規定瀏覽 API

GET /api/curriculum/tree               → 學院 → 系所/學士班 階層樹
GET /api/curriculum/dept/{id}          → 系所完整資料（from curriculum_requirements_114.json）
GET /api/curriculum/notes              → requirements_notes.json 全部內容
GET /api/curriculum/notes/{dept_name} → 指定系所的 raw_text 參考資料
"""

import json
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, HTTPException

router = APIRouter()

BASE = Path(__file__).parent.parent.parent.parent
CURRICULUM_PATH = BASE / "data" / "processed" / "curriculum_requirements_114.json"
NOTES_PATH      = BASE / "data" / "processed" / "requirements_notes.json"

# ── module-level cache ───────────────────────────────────────────────────────

_curriculum_cache: Optional[dict] = None
_notes_cache: Optional[dict]      = None
_name_to_id_cache: Optional[dict] = None   # {dept_name: dept_id}
_id_to_name_cache: Optional[dict] = None   # {dept_id: dept_name}


def _load_curriculum() -> dict:
    global _curriculum_cache
    if _curriculum_cache is None:
        with open(CURRICULUM_PATH, encoding="utf-8") as f:
            _curriculum_cache = json.load(f)
    return _curriculum_cache


def _load_notes() -> dict:
    global _notes_cache
    if _notes_cache is None:
        if NOTES_PATH.exists():
            with open(NOTES_PATH, encoding="utf-8") as f:
                _notes_cache = json.load(f)
        else:
            _notes_cache = {}
    return _notes_cache


def _build_name_id_maps() -> tuple[dict, dict]:
    global _name_to_id_cache, _id_to_name_cache
    if _name_to_id_cache is not None:
        return _name_to_id_cache, _id_to_name_cache
    data = _load_curriculum()
    n2i, i2n = {}, {}

    def _register(node: dict):
        nid  = node.get("id", "")
        name = node.get("name", "")
        if nid and name:
            n2i[name] = nid
            i2n[nid]  = name

    def _register_all(node: dict):
        _register(node)
        for child in node.get("groups", []):
            _register_all(child)
        for child in node.get("specialization_tracks", []):
            _register_all(child)

    for college in data.get("colleges", []):
        for dept in college.get("departments", []):
            _register_all(dept)
        for cbp in college.get("college_bachelor_programs", []):
            _register_all(cbp)

    _name_to_id_cache = n2i
    _id_to_name_cache = i2n
    return n2i, i2n


# ── 遞迴尋找系所節點 ─────────────────────────────────────────────────────────

def _find_node_with_parent(data: dict, target_id: str) -> tuple[Optional[dict], list[dict]]:
    def _search(node: dict, ancestors: list[dict]) -> tuple[Optional[dict], list[dict]]:
        if node.get("id") == target_id:
            return node, ancestors
        for child in node.get("groups", []) + node.get("specialization_tracks", []):
            found, parent_chain = _search(child, ancestors + [node])
            if found is not None:
                return found, parent_chain
        return None, []

    for college in data.get("colleges", []):
        for dept in college.get("departments", []):
            found, parent_chain = _search(dept, [])
            if found is not None:
                return found, parent_chain
        for cbp in college.get("college_bachelor_programs", []):
            found, parent_chain = _search(cbp, [])
            if found is not None:
                return found, parent_chain
    return None, []


# ── 規則分類 ─────────────────────────────────────────────────────────────────

_RULE_CATEGORY: dict[str, str] = {
    "credit_minimum": "學分規定", "dept_required": "學分規定",
    "elective_min": "學分規定", "elective_minimum": "學分規定",
    "common_required": "學分規定", "total_required": "學分規定",
    "dept_elective_min": "學分規定", "elective_total_min": "學分規定",
    "free_elective": "學分規定", "free_elective_min": "學分規定",
    "school_elective_min": "學分規定", "dept_school_elective_min": "學分規定",
    "cross_college_elective": "學分規定", "cross_college_elective_min": "學分規定",
    "outside_elective_min": "學分規定", "outside_elective_max": "學分規定",
    "dept_system_elective": "學分規定", "core_elective_min": "學分規定",
    "cross_group_elective": "學分規定", "ch_elective_min": "學分規定",
    "star_elective_min": "學分規定", "triangle_elective_min": "學分規定",
    "capstone_elective_min": "學分規定", "other_elective_min": "學分規定",
    "second_domain_minimum": "學分規定", "first_domain_minimum": "學分規定",
    "professional_minimum": "學分規定", "foundation_required": "學分規定",
    "dept_courses_min": "學分規定", "language_training_minimum": "學分規定",
    "domain_elective": "學分規定", "elective_fail_note": "學分規定",
    "cross_domain_required": "學分規定", "cross_domain": "學分規定",
    "college_required": "學分規定", "college_elective_min": "學分規定",
    "college_and_dept_required": "學分規定", "additional_required": "學分規定",
    "required_elective_min": "學分規定", "elective_note": "學分規定",
    "ph_elective_min": "學分規定", "dept_elective_gp": "學分規定",
    "science_required_min": "學分規定",
    "design_course_min": "指定選課", "required_elective": "指定選課",
    "law_finance_group": "指定選課", "capstone_credit_limit": "指定選課",
    "internship_limit": "指定選課", "natural_science_select": "指定選課",
    "group_required": "指定選課", "earth_system_required": "指定選課",
    "basic_science_two_of_three_groups": "指定選課", "lab_one_of_three": "指定選課",
    "core_elective_ab": "指定選課", "core_elective_each_group": "指定選課",
    "prerequisite": "先修條件", "prerequisite_note": "先修條件",
    "prerequisite_calculus_to_engineering_math": "先修條件",
    "prerequisite_program_design": "先修條件",
    "prerequisite_project_sequence": "先修條件",
    "prerequisite_thesis": "先修條件",
    "social_practice_prerequisite": "先修條件",
    "certification_required": "外部認證", "certification_waiver": "外部認證",
    "cpe_certification": "外部認證", "foreign_language": "外部認證",
    "restriction": "特殊規定", "course_substitution": "特殊規定",
    "course_substitution_limit": "特殊規定", "substitution": "特殊規定",
    "equivalent_courses": "特殊規定", "equivalent_course_note": "特殊規定",
    "double_major_extra_elective": "特殊規定",
    "general_education": "特殊規定", "general_education_limit": "特殊規定",
    "general_education_required": "特殊規定",
    "emi_track_requirement": "特殊規定", "digital_literacy": "特殊規定",
    "design_thinking": "特殊規定", "early_graduation": "特殊規定",
    "cross_dept_elective_limit": "特殊規定", "secondary_track_optional": "特殊規定",
    "specialization_minimum": "特殊規定", "specialization_track": "特殊規定",
    "group_split": "特殊規定", "program_choice": "特殊規定",
    "program_elective": "特殊規定", "special_requirement": "特殊規定",
    "special_requirement_one_of": "特殊規定", "capstone_mutual_exclusion": "特殊規定",
    "thesis_requirement": "特殊規定", "academic_ethics_course": "特殊規定",
    "science_ability_required": "特殊規定",
}


def _rule_category(rule_type: str) -> str:
    return _RULE_CATEGORY.get(rule_type, "其他規定")


def _enrich_rules(rules: list) -> list:
    return [{**r, "category": _rule_category(r.get("type", ""))} for r in rules]


# ── 端點 ────────────────────────────────────────────────────────────────────

@router.get("/tree")
def get_curriculum_tree() -> list[dict]:
    """學院 → 系所/學院學士班 的輕量階層樹。"""
    data = _load_curriculum()
    result = []
    for college in data.get("colleges", []):
        college_node: dict[str, Any] = {
            "id":   college["id"],
            "name": college["name"],
            "departments": [],
            "college_bachelor_programs": [],
        }
        for dept in college.get("departments", []):
            node: dict[str, Any] = {
                "id":           dept["id"],
                "name":         dept["name"],
                "program_type": dept.get("program_type", "traditional_dept"),
                "min_credits":  dept.get("min_credits", 0),
            }
            if dept.get("program_type") == "dept_with_groups":
                node["groups"] = [
                    {"id": g["id"], "name": g["name"],
                     "group_label": g.get("group_label", "")}
                    for g in dept.get("groups", [])
                ]
            college_node["departments"].append(node)
        for cbp in college.get("college_bachelor_programs", []):
            college_node["college_bachelor_programs"].append({
                "id":           cbp["id"],
                "name":         cbp["name"],
                "program_type": cbp.get("program_type", "college_bachelor"),
                "min_credits":  cbp.get("min_credits", 0),
                "specialization_tracks": [
                    {"id": t["id"], "name": t["name"]}
                    for t in cbp.get("specialization_tracks", [])
                ],
            })
        result.append(college_node)
    return result


@router.get("/dept/{dept_id}")
def get_dept_detail(dept_id: str) -> dict:
    """系所完整資料（含 category 欄位的 graduation_rules），支援從父層繼承。"""
    data = _load_curriculum()
    node, parent = _find_node_with_parent(data, dept_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"找不到系所：{dept_id}")
    
    node = dict(node)
    
    if parent:
        INHERITABLE_LIST_FIELDS = [
            "required_courses", "foundation_courses", "college_required_courses",
            "common_required_courses", "dept_required_courses", "required_electives",
            "cross_domain_required", "earth_system_courses", "cross_group_required",
            "application_courses", "first_domain_electives", "elective_courses",
            "elective_groups", "core_elective_groups", "college_required_elective_groups",
            "science_ability_groups", "other_elective_groups"
        ]

        for field in INHERITABLE_LIST_FIELDS:
            merged = list(node.get(field, []) or [])
            for anc in parent:
                ancestor_list = anc.get(field, []) or []
                if ancestor_list:
                    merged = merged + ancestor_list if merged else ancestor_list
            if merged:
                node[field] = merged

        # 繼承畢業規定
        merged_rules = list(node.get("graduation_rules", []) or [])
        for anc in parent:
            ancestor_rules = anc.get("graduation_rules", []) or []
            if ancestor_rules:
                merged_rules = merged_rules + ancestor_rules
        node["graduation_rules"] = merged_rules

        # 繼承學分設定
        for key in ("min_credits", "required_credits"):
            if key not in node or node.get(key) is None:
                for anc in parent:
                    if key in anc and anc.get(key) is not None:
                        node[key] = anc[key]
                        break

    node["graduation_rules"] = _enrich_rules(node.get("graduation_rules", []))
    return node


@router.get("/notes")
def get_all_notes() -> dict:
    """回傳 requirements_notes.json 全部內容。"""
    return _load_notes()


@router.get("/notes/by-id/{dept_id}")
def get_notes_by_id(dept_id: str) -> dict:
    """以系所 id 查找對應的 requirements_notes 條目。"""
    notes = _load_notes()
    _, i2n = _build_name_id_maps()
    dept_name = i2n.get(dept_id, "")

    # 精確比對或部分比對
    if dept_name in notes:
        return {"dept_id": dept_id, "dept_name": dept_name,
                "entries": [{"key": dept_name, **notes[dept_name]}]}

    # 模糊比對：找所有以 dept_name 開頭或包含的 key
    matched = {k: v for k, v in notes.items()
               if dept_name and (k.startswith(dept_name) or dept_name in k)}
    if matched:
        return {"dept_id": dept_id, "dept_name": dept_name,
                "entries": [{"key": k, **v} for k, v in matched.items()]}

    return {"dept_id": dept_id, "dept_name": dept_name, "entries": []}

from fastapi.responses import FileResponse

PDF_BASE = BASE / "data" / "raw" / "應修科目表"

@router.get("/pdf/{dept_id}")
def get_curriculum_pdf(dept_id: str):
    """取得指定系所的原始應修科目表 PDF"""
    # ─── 將文學院學士班分組的 ID 映射至文學院學士班的主 ID ───
    if dept_id in {"track_philosophy", "track_history", "track_art_history", "track_image_narrative"}:
        dept_id = "cbp_liberal_arts"

    _, i2n = _build_name_id_maps()
    dept_name = i2n.get(dept_id, "")
    if not dept_name:
        raise HTTPException(status_code=404, detail="找不到系所")

    if not PDF_BASE.exists():
        raise HTTPException(status_code=404, detail="PDF 目錄不存在")

    # 在目錄中遞迴尋找包含系所名稱的 PDF 檔案
    # 優先尋找完全匹配的檔名，例如 "資訊工程學系_114.pdf"
    for path in PDF_BASE.rglob("*.pdf"):
        if dept_name in path.name:
            return FileResponse(path, media_type="application/pdf", filename=path.name)

    raise HTTPException(status_code=404, detail=f"找不到對應的 PDF ({dept_name})")
