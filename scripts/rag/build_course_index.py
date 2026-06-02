"""
build_course_index.py

整合以下資料來源，產出 data/processed/course_index.json：
  - courses_deduped/undergrad.json  課程基本資料 + 分發條件（含多班別）
  - courses_deduped/grad.json       研究所課程
  - nlp/nlp_tech_nodes.json         概念 / 程式語言 / 工具
  - nlp/nlp_topic_tags.json         主題標籤 / 核心議題
  - nlp/nlp_simplified_concepts.json  概念白話說明
  - nlp/nlp_domain_tags.json        領域標籤
  - schedule_draft/**/*.json        建議修習學期
  - course_eligibility.json         prereq_codes（修課關係）

index key：base course_code（去掉 -班別 後綴）
同一課號若有多班，各班差異（teacher、dept、eligibility_text）存入 sections 陣列。
NLP / 學期等共用資料只存一份在外層。

執行方式：
  python scripts/rag/build_course_index.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT       = Path(__file__).parent.parent.parent
DATA_PROC  = ROOT / "data" / "processed"
DATA_RAW   = ROOT / "data" / "raw"

OUT_PATH   = DATA_PROC / "course_index.json"

DEDUPED_UG      = DATA_PROC / "courses_deduped" / "undergrad.json"
DEDUPED_GRAD    = DATA_PROC / "courses_deduped" / "grad.json"
NLP_DIR         = DATA_PROC / "nlp"
SCHEDULE_DIR    = DATA_PROC / "schedule_draft"
CURRICULUM_REQ  = DATA_PROC / "curriculum_requirements_114.json"
ELIGIBILITY     = DATA_PROC / "course_eligibility.json"


# ── 工具 ─────────────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clean_code(raw: str) -> str:
    """'CE2002-A' → 'CE2002'"""
    return raw.split("-")[0].strip() if raw else ""


def format_condition(cond) -> str:
    """將 courses_deduped 的 分發條件 dict 轉成可讀文字。

    格式一：{'優先順序列表': [{'優先順序': '1', '相關條件限制說明': '...'}]}
    格式二：{'限制說明': '課程沒有限制'}
    """
    if not cond or not isinstance(cond, dict):
        return ""

    if "限制說明" in cond:
        return cond["限制說明"]

    parts = []
    for item in cond.get("優先順序列表", []):
        p = item.get("優先順序", "")
        desc = item.get("相關條件限制說明", "").strip()
        if desc:
            parts.append(f"P{p}: {desc}" if p else desc)
    return " | ".join(parts)


# ── 載入 NLP 資料 ─────────────────────────────────────────────────────────────

def load_nlp() -> dict:
    """回傳 {course_code: {concepts, languages, tools, topic_tags, core_questions,
                           simplified_concepts, domain_tags}}"""
    tech_map    = load_json(NLP_DIR / "nlp_tech_nodes.json")       if (NLP_DIR / "nlp_tech_nodes.json").exists()         else {}
    topic_map   = load_json(NLP_DIR / "nlp_topic_tags.json")       if (NLP_DIR / "nlp_topic_tags.json").exists()         else {}
    simp_map    = load_json(NLP_DIR / "nlp_simplified_concepts.json") if (NLP_DIR / "nlp_simplified_concepts.json").exists() else {}
    domain_map  = load_json(NLP_DIR / "nlp_domain_tags.json")      if (NLP_DIR / "nlp_domain_tags.json").exists()        else {}

    all_codes = set(tech_map) | set(topic_map) | set(simp_map) | set(domain_map)
    result = {}
    for code in all_codes:
        tech   = tech_map.get(code, {})
        topic  = topic_map.get(code, {})
        simp   = simp_map.get(code, {})
        domain = domain_map.get(code, {})

        raw_domain = domain.get("domain_tags", [])
        domain_tags = []
        if isinstance(raw_domain, list):
            for tag in raw_domain:
                if isinstance(tag, dict) and tag.get("field"):
                    domain_tags.append({"field": tag["field"], "relevance": tag.get("relevance", "medium")})
                elif isinstance(tag, str):
                    domain_tags.append({"field": tag, "relevance": "medium"})

        result[code] = {
            "concepts":           tech.get("concepts", []),
            "languages":          tech.get("languages", []),
            "tools":              tech.get("tools", []),
            "topic_tags":         topic.get("topic_tags", []),
            "core_questions":     topic.get("core_questions", []),
            "simplified_concepts": simp.get("simplified_concepts", []),
            "domain_tags":        domain_tags,
        }

    print(f"[NLP] 載入 {len(result)} 筆")
    return result


# ── 載入 schedule（建議學期）─────────────────────────────────────────────────

def load_schedule() -> dict[str, list[dict]]:
    """從 curriculum_requirements_114.json 讀取全部層級，
    回傳 {course_code: [{dept_id, dept_name, when}, ...]}。

    相較於舊的逐檔掃描 + setdefault，此版本：
    - 覆蓋所有層級（groups / specialization_tracks / 其子群組）
    - 保留同一門課被多科系必修的完整資訊（43 門多科系課程）
    """
    from collections import defaultdict
    lookup: defaultdict[str, list[dict]] = defaultdict(list)

    if not CURRICULUM_REQ.exists():
        print(f"[WARN] {CURRICULUM_REQ} 不存在，schedule 將為空")
        return {}

    data = load_json(CURRICULUM_REQ)

    def walk(node: dict, dept_id: str, dept_name: str):
        for rc in node.get("required_courses", []):
            code = rc.get("code", "").strip()
            when = rc.get("when", "")
            if code and when:
                # 去重：同一 dept_id 只記一次
                if not any(e["dept_id"] == dept_id for e in lookup[code]):
                    lookup[code].append({"dept_id": dept_id, "dept_name": dept_name, "when": when})
        for track in node.get("specialization_tracks", []):
            walk(track, track.get("id", dept_id), track.get("name", dept_name))
        for grp in node.get("groups", []):
            walk(grp, grp.get("id", dept_id), grp.get("name", dept_name))

    for college in data.get("colleges", []):
        for dept in college.get("departments", []):
            walk(dept, dept.get("id", ""), dept.get("name", ""))
        for cbp in college.get("college_bachelor_programs", []):
            walk(cbp, cbp.get("id", ""), cbp.get("name", ""))

    result = dict(lookup)
    multi = sum(1 for v in result.values() if len(v) > 1)
    print(f"[Schedule] 載入 {len(result)} 筆（其中 {multi} 門為多科系必修）")
    return result


# ── 載入 eligibility（先修/衝堂關係）────────────────────────────────────────

def load_eligibility_relations() -> dict[str, dict]:
    """只取 prereq / coreq / conflict codes，不取 raw_conditions（改用課程原始分發條件）。"""
    lookup: dict[str, dict] = {}
    if not ELIGIBILITY.exists():
        return lookup
    data = load_json(ELIGIBILITY)
    for entry in data:
        code = entry.get("course_code", "").strip()
        if not code:
            continue
        rels = entry.get("course_relations") or {}
        lookup[code] = {
            "prereq_codes":   rels.get("prereq_codes", []),
            "coreq_codes":    rels.get("coreq_codes", []),
            "conflict_codes": rels.get("conflict_codes", []),
        }
    print(f"[Eligibility] 載入 {len(lookup)} 筆")
    return lookup


# ── 整合課程資料 ──────────────────────────────────────────────────────────────

def build_index(
    courses: list[dict],
    nlp: dict,
    schedule: dict,
    elig_rel: dict,
    is_grad: bool,
) -> dict[str, dict]:
    """以 base code 為 key，整合各來源資料。"""

    # 先依 base code 分組
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in courses:
        raw_code = c.get("課號-班別", "")
        base = clean_code(raw_code)
        if base:
            groups[base].append(c)

    index: dict[str, dict] = {}

    for base_code, section_list in groups.items():
        # 取第一個 section 的共用資料（課名、課綱目標內容相同）
        first = section_list[0]
        syllabus = first.get("課程綱要") or {}
        if isinstance(syllabus, str):
            syllabus = {}

        name_zh  = syllabus.get("課程名稱(中文)") or first.get("課程名稱(中文)", "")
        name_en  = syllabus.get("課程名稱(英文)") or first.get("課程名稱(英文)", "")
        credits  = syllabus.get("學分") or first.get("學分", 0)
        try:
            credits = int(credits)
        except (ValueError, TypeError):
            credits = 0

        objective = syllabus.get("課程目標", "") or ""
        content   = syllabus.get("授課內容", "") or ""
        textbook  = syllabus.get("教科書/參考書", "") or ""

        # 課程領域（以「、」分隔，切開後去空白、去重複）
        raw_domains = syllabus.get("課程領域", "") or ""
        course_domains = list(dict.fromkeys(
            d.strip() for d in raw_domains.split("、") if d.strip()
        ))

        # NLP 共用資料（by base_code）
        nlp_data = nlp.get(base_code, {})

        # 建議學期（多科系必修時保留完整列表）
        when_schedule: list[dict] = schedule.get(base_code, [])

        # 修課關係（prereq/coreq/conflict）
        rel = elig_rel.get(base_code, {})

        # ── 建 sections 陣列（每班的差異資料）──
        sections = []
        for c in section_list:
            raw_code_full = c.get("課號-班別", "")
            section_id = raw_code_full.split("-")[1].strip() if "-" in raw_code_full else ""

            c_syllabus = c.get("課程綱要") or {}
            if isinstance(c_syllabus, str):
                c_syllabus = {}

            teacher = c.get("授課教師", "") or ""
            dept    = c.get("系所", "") or c_syllabus.get("開課單位", "")
            college = c.get("學院", "") or ""
            type_   = c.get("選修別", "") or ""

            # 分發條件（原始 dict → 可讀字串）
            eligibility_text = format_condition(c.get("分發條件"))

            sec_obj  = (c_syllabus.get("課程目標", "") or "").strip()
            sec_cont = (c_syllabus.get("授課內容", "") or "").strip()
            sec_tb   = (c_syllabus.get("教科書/參考書", "") or "").strip()

            sections.append({
                "section":          section_id,
                "teacher":          teacher,
                "dept":             dept,
                "college":          college,
                "type":             type_,
                "eligibility_text": eligibility_text,
                "course_objective": sec_obj,
                "course_content":   sec_cont,
                "textbook":         sec_tb,
            })

        # 如果只有一個 section 且沒有 section id，把 dept/teacher 提到外層
        single = len(sections) == 1
        outer_dept    = sections[0]["dept"]    if single else ""
        outer_college = sections[0]["college"] if single else ""
        outer_teacher = sections[0]["teacher"] if single else ""
        outer_type    = sections[0]["type"]    if single else (sections[0]["type"] if sections else "")
        outer_elig    = sections[0]["eligibility_text"] if single else ""

        index[base_code] = {
            # 基本資訊
            "name_zh":   name_zh,
            "name_en":   name_en,
            "credits":   credits,
            "is_grad":   is_grad,
            # 單班課程直接放外層，多班留空（查 sections）
            "dept":      outer_dept,
            "college":   outer_college,
            "teacher":   outer_teacher,
            "type":      outer_type,
            # 課綱
            "objective": objective,
            "content":   content,
            "textbook":  textbook,
            # 修習資訊（when_schedule：完整多科系列表）
            "when_schedule": when_schedule,
            "prereq_codes":  rel.get("prereq_codes", []),
            "coreq_codes":   rel.get("coreq_codes", []),
            "conflict_codes": rel.get("conflict_codes", []),
            # NLP 資料
            "concepts":             nlp_data.get("concepts", []),
            "languages":            nlp_data.get("languages", []),
            "tools":                nlp_data.get("tools", []),
            "topic_tags":           nlp_data.get("topic_tags", []),
            "core_questions":       nlp_data.get("core_questions", []),
            "simplified_concepts":  nlp_data.get("simplified_concepts", []),
            "domain_tags":          nlp_data.get("domain_tags", []),
            "course_domains":       course_domains,
            # 多班差異
            "sections": [] if single else sections,
            # 單班的分發條件直接放外層
            "eligibility_text": outer_elig,
        }

    return index


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    print("載入 NLP 資料...")
    nlp = load_nlp()

    print("載入 schedule 資料...")
    schedule = load_schedule()

    print("載入 eligibility 關係...")
    elig_rel = load_eligibility_relations()

    index: dict[str, dict] = {}

    if DEDUPED_UG.exists():
        ug_courses = load_json(DEDUPED_UG)
        print(f"大學部課程：{len(ug_courses)} 筆")
        ug_index = build_index(ug_courses, nlp, schedule, elig_rel, is_grad=False)
        index.update(ug_index)
        print(f"  → {len(ug_index)} 個 base code")
    else:
        print(f"[WARN] 找不到 {DEDUPED_UG}")

    if DEDUPED_GRAD.exists():
        grad_courses = load_json(DEDUPED_GRAD)
        print(f"研究所課程：{len(grad_courses)} 筆")
        grad_index = build_index(grad_courses, nlp, schedule, elig_rel, is_grad=True)
        # 研究所課號若與大學部衝突，以大學部為主（通常不會衝突）
        for k, v in grad_index.items():
            if k not in index:
                index[k] = v
        print(f"  → {len(grad_index)} 個 base code（新增 {sum(1 for k in grad_index if k not in index)} 筆）")
    else:
        print(f"[WARN] 找不到 {DEDUPED_GRAD}")

    # 統計多班課程數量
    multi_section = sum(1 for v in index.values() if v["sections"])
    print(f"\n合計：{len(index)} 個 base code，其中 {multi_section} 個有多班")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_PATH.stat().st_size / 1024 / 1024
    print(f"\n✓ 已寫出 {OUT_PATH}")
    print(f"  大小：{size_mb:.1f} MB")


if __name__ == "__main__":
    main()
