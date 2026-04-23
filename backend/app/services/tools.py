"""
tools.py

ReAct Tool-Use 工具定義與執行器。
每個 tool_* 函式對應一個 OpenAI function schema，
execute_tool() 依工具名稱分派執行。
"""

import inspect
import json
from functools import lru_cache
from pathlib import Path

from app.services import retriever, graph_service

ROOT = Path(__file__).parent.parent.parent.parent


@lru_cache(maxsize=1)
def _load_program_descriptions() -> dict:
    path = ROOT / "data" / "processed" / "program_descriptions.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@lru_cache(maxsize=1)
def _load_requirements_notes() -> dict:
    path = ROOT / "data" / "processed" / "requirements_notes.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ── 結果格式化 ────────────────────────────────────────────────────────────────

def _fmt_courses(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        m = r.get("metadata", {})
        langs    = m.get("languages", "") or ""
        tools_s  = m.get("tools", "") or ""
        tech_parts = [x.strip() for x in (langs + "," + tools_s).split(",") if x.strip()]
        out.append({
            "course_code":  m.get("course_code", ""),
            "name_zh":      m.get("name_zh", ""),
            "name_en":      m.get("name_en", ""),
            "dept":         m.get("dept", ""),
            "college":      m.get("college", ""),
            "credits":      m.get("credits", 0),
            "type":         m.get("type", ""),
            "teacher":      m.get("teacher", ""),
            "when_raw":     m.get("when_raw", ""),
            "concepts":     m.get("concepts", ""),
            "technologies": ", ".join(tech_parts),
            "domain_tags":  m.get("domain_tags", ""),
            "summary":      r.get("document", "")[:200],
            "distance":     round(r.get("distance", 0.0), 4),
        })
    return out


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def tool_search_courses(
    query: str,
    dept: str = None,
    college: str = None,
    course_type: str = None,
    year: int = None,
    sem: int = None,
    tech: str = None,
    is_grad: bool = False,
    exclude_grad_only: bool = True,
    n: int = 8,
) -> list[dict]:
    """語意搜尋課程，組裝 ChromaDB filters 後呼叫 retriever。
    若 tech 有值，會先走 graph 精確查詢，再補上向量搜尋結果。

    【Fallback】若回傳結果 < 3 筆，嘗試：
    1. 移除 tech 參數，改用純語意搜尋
    2. 換成更短的關鍵字（如只保留核心詞）
    3. 改用 find_similar_courses 尋找概念相關課程
    """
    # Graph-first：tech 查詢先走圖，結果最精確
    if tech:
        graph_hits = graph_service.search_courses_by_tech(tech)
        if graph_hits:
            # 篩選等級（研究所/大學部）
            level_filter = "grad" if is_grad else "ugrad"
            filtered = [c for c in graph_hits if c.get("level", "ugrad") == level_filter]
            if not filtered:
                filtered = graph_hits  # 若沒符合等級，仍回傳全部
            return [
                {
                    "course_code": c["id"],
                    "name_zh":     c["name"],
                    "dept":        c["dept"],
                    "credits":     c.get("credits"),
                    "tech_node":   c.get("tech_node", ""),
                    "source":      "graph_tech",
                    # 其餘欄位留空，vector search 沒額外資料
                    "name_en": "", "college": "", "type": "", "teacher": "",
                    "teacher_specialties": "", "when_raw": "", "prereq_codes": "",
                    "eligible_years": "", "languages": "", "tools": "",
                    "domain_tags": "", "summary": "",
                }
                for c in filtered[:n * 2]
            ]

    # 用 conditions list 累積，最後組成合法的 ChromaDB where 語法
    # 避免 {"dept": "X", "$or": [...]} 這種非法混合格式
    conditions: list[dict] = []
    if dept:
        conditions.append({"dept": {"$eq": dept}})
    if college:
        conditions.append({"college": {"$eq": college}})
    if course_type:
        conditions.append({"type": {"$eq": course_type}})
    if year is not None and sem is not None:
        conditions.append({"when_semesters": {"$contains": f"{year}_{sem}"}})
    elif year is not None:
        conditions.append({"$or": [
            {"when_semesters": {"$contains": f"{year}_1"}},
            {"when_semesters": {"$contains": f"{year}_2"}},
        ]})
    if exclude_grad_only and not is_grad:
        conditions.append({"is_grad_only": {"$eq": False}})
    if tech:
        conditions.append({"$or": [
            {"tools":     {"$contains": tech}},
            {"languages": {"$contains": tech}},
            {"concepts":  {"$contains": tech}},
        ]})

    if len(conditions) == 0:
        filters = None
    elif len(conditions) == 1:
        filters = conditions[0]
    else:
        filters = {"$and": conditions}

    collection = "ncu_courses_grad" if is_grad else "ncu_courses_ug"
    results = retriever.search_courses(
        query, filters=filters, n_results=n, collection=collection
    )
    return _fmt_courses(results)


def tool_get_dept_courses(dept_name: str, course_type: str = "required") -> dict:
    """圖查詢系所必修或選修課程。圖缺資料時自動 fallback 至 ChromaDB 精確過濾。

    【Fallback】若系所名稱找不到，嘗試：
    1. 只用關鍵部分（如「資工」而非「資訊工程學系」）
    2. 呼叫 search_courses(dept="...", n=20) 做向量補充
    """
    if course_type == "required":
        courses = graph_service.get_dept_required_courses(dept_name)
    elif course_type == "elective":
        courses = graph_service.get_dept_elective_courses(dept_name)
        if not courses:
            # Fallback：用 ChromaDB 精確 get（dept+type 雙重過濾，不受向量搜尋上限影響）
            raw = retriever.get_courses_by_dept_type(dept_name, "選修")
            courses = [
                {
                    "id":       r["id"],
                    "name":     r["metadata"].get("name_zh", ""),
                    "credits":  r["metadata"].get("credits"),
                    "relation": "選修",
                    "teacher":  r["metadata"].get("teacher", ""),
                }
                for r in raw
            ]
    else:
        req  = graph_service.get_dept_required_courses(dept_name)
        elec = graph_service.get_dept_elective_courses(dept_name)
        if not elec:
            raw  = retriever.get_courses_by_dept_type(dept_name, "選修")
            elec = [
                {"id": r["id"], "name": r["metadata"].get("name_zh", ""),
                 "credits": r["metadata"].get("credits"), "relation": "選修"}
                for r in raw
            ]
        courses = req + elec
    return {"dept_name": dept_name, "course_type": course_type, "courses": courses}


def tool_get_program_courses(program_name: str) -> dict:
    """圖查詢學分學程的必/選修課程。"""
    courses = graph_service.get_program_courses(program_name)
    return {"program_name": program_name, "courses": courses}


def tool_get_teacher_info(teacher_name: str) -> dict:
    """查詢特定教師的專長資料（CSV）與開課清單（圖）。"""
    profile_raw = retriever.get_teacher_by_name(teacher_name)
    courses = graph_service.get_teacher_courses(teacher_name)
    profile = [
        {
            "name":        r.get("metadata", {}).get("name", teacher_name),
            "dept":        r.get("metadata", {}).get("dept", ""),
            "rank":        r.get("metadata", {}).get("rank", ""),
            "specialties": r.get("metadata", {}).get("specialties", ""),
        }
        for r in profile_raw
    ]
    return {"teacher_name": teacher_name, "profile": profile, "courses": courses}


def tool_search_teachers(query: str, n: int = 5) -> list[dict]:
    """依研究領域或專長關鍵詞語意搜尋教師。"""
    results = retriever.search_teachers(query, n_results=n)
    return [
        {
            "name":        r.get("metadata", {}).get("name", ""),
            "dept":        r.get("metadata", {}).get("dept", ""),
            "rank":        r.get("metadata", {}).get("rank", ""),
            "specialties": r.get("metadata", {}).get("specialties", ""),
        }
        for r in results
    ]


def tool_get_prereq_info(course_query: str) -> dict:
    """搜尋目標課程後展開 prereq_codes，回傳先修課詳情。"""
    results = retriever.search_courses(course_query, n_results=3)
    if not results:
        return {"found": False, "message": f"找不到「{course_query}」的相關課程"}
    meta = results[0].get("metadata", {})
    prereq_str = meta.get("prereq_codes", "")
    prereq_details = []
    if prereq_str:
        for code in prereq_str.split(","):
            code = code.strip()
            if not code:
                continue
            for r in retriever.get_courses_by_code(code):
                m = r.get("metadata", {})
                prereq_details.append({
                    "course_code": m.get("course_code", code),
                    "name_zh":     m.get("name_zh", code),
                    "credits":     m.get("credits", 0),
                    "dept":        m.get("dept", ""),
                    "when_raw":    m.get("when_raw", ""),
                })
    return {
        "target_course": meta.get("name_zh", ""),
        "course_code":   meta.get("course_code", ""),
        "prereq_codes":  prereq_str,
        "prereq_details": prereq_details,
        "has_prereq":    bool(prereq_str),
    }


def tool_get_graduation_rules(dept_name: str) -> dict:
    """從 schedule_draft 取得系所畢業學分規定與認證要求。"""
    result = graph_service.get_graduation_rules(dept_name)
    if not result:
        return {"found": False, "message": f"找不到「{dept_name}」的畢業規定資料"}
    return result


def tool_get_dept_info(query: str) -> list[dict]:
    """語意搜尋系所介紹（Collego 資料：特色、生涯進路、能力特質）。"""
    results = retriever.search_departments(query, n_results=5)
    return [
        {
            "dept_name": r.get("metadata", {}).get("dept_name", ""),
            "summary":   r.get("document", "")[:500],
        }
        for r in results
    ]


def _matches_access_rule(rule: dict, student_dept: str, student_year: int,
                          program_type: str = "bachelor",
                          minor_depts: list | None = None,
                          double_major_depts: list | None = None,
                          student_college: str = "") -> bool:
    """回傳 True 表示此 rule 允許該學生修課。空 list = 不限制。"""
    minor_depts = minor_depts or []
    double_major_depts = double_major_depts or []

    # 學制檢查（空 = 不限）
    if rule["program_types"] and program_type not in rule["program_types"]:
        return False

    # 年級檢查（空 = 不限）
    if rule["years"] and student_year not in rule["years"]:
        return False

    # 系所/學院：兩者皆空 = 不限；否則符合任一即可
    no_restriction = not rule["dept_include"] and not rule["college_include"]
    dept_ok    = no_restriction or (student_dept in rule["dept_include"])
    college_ok = no_restriction or (bool(student_college) and student_college in rule["college_include"])
    minor_ok   = rule["open_to_minor"] and (
        not rule["minor_include"] or any(d in rule["minor_include"] for d in minor_depts)
    )
    double_ok  = rule["open_to_double_major"] and (
        not rule["double_major_include"] or any(d in rule["double_major_include"] for d in double_major_depts)
    )
    if not (dept_ok or college_ok or minor_ok or double_ok):
        return False

    # 排除檢查
    if student_dept in rule.get("dept_exclude", []):
        return False
    if student_college and student_college in rule.get("college_exclude", []):
        return False

    return True


def can_student_take(course_metadata: dict, student_dept: str, student_year: int,
                     program_type: str = "bachelor",
                     minor_depts: list | None = None,
                     double_major_depts: list | None = None) -> bool:
    """
    給定課程 metadata 與學生資料，判斷是否可修。
    course_metadata 需含 access_rules（v3 格式）或 is_unrestricted（舊格式 fallback）。
    """
    if course_metadata.get("is_unrestricted"):
        return True
    access_rules = course_metadata.get("access_rules")
    if access_rules is None:
        return True
    student_college = retriever.get_dept_college(student_dept)
    return any(
        _matches_access_rule(r, student_dept, student_year, program_type,
                             minor_depts, double_major_depts, student_college)
        for r in access_rules
    )


def tool_get_course_eligibility(course_query: str) -> dict:
    """查詢課程的修課資格限制（年級、系所、是否開放外系等）。

    回傳 raw_conditions 原文，讓 LLM 直接理解分發條件。
    有多門同名課程時全部回傳，由 LLM 判斷哪門是使用者詢問的。
    """
    def _fmt_elig(m: dict) -> dict:
        code = m.get("course_code", "")
        elig = retriever.get_course_eligibility(code)
        raw_list = elig.get("raw_conditions", [])
        if elig.get("is_unrestricted"):
            raw_conditions = "不限修課條件（全校皆可修）"
        elif raw_list:
            raw_conditions = " | ".join(raw_list)
        else:
            raw_conditions = "無詳細分發條件資料"
        return {
            "course_code":   code,
            "name_zh":       m.get("name_zh", ""),
            "dept":          m.get("dept", ""),
            "raw_conditions": raw_conditions,
        }

    exact = retriever.get_courses_by_name(course_query)
    if exact:
        return {
            "found": True,
            "match_type": "exact",
            "courses": [_fmt_elig(r["metadata"]) for r in exact],
        }

    results = retriever.search_courses(course_query, n_results=5)
    if not results:
        return {"found": False, "message": f"找不到「{course_query}」"}
    return {
        "found": True,
        "match_type": "semantic",
        "courses": [_fmt_elig(r["metadata"]) for r in results],
    }


def tool_get_course_knowledge_map(course_name: str) -> str:
    """回傳一門課的知識地圖：學什麼概念、用什麼技術、哪些課程與它概念重疊最高。

    【使用時機】使用者問「演算法在學什麼？」「機器學習這門課教哪些東西？」
    「有沒有和機器學習類似的課？」等探索式問題時使用。
    比純語意搜尋更能呈現課程的完整知識結構。
    """
    result = graph_service.get_course_knowledge_map(course_name)
    if not result:
        return f"找不到「{course_name}」的課程資料（請嘗試更短的關鍵詞）。"

    lines = []
    c = result["course"]
    lines.append(f"【{c['name']}】（{c['dept']}，{c.get('credits', '?')}學分）")

    techs = result.get("technologies", [])
    if techs:
        lines.append(f"\n使用技術：{', '.join(t['name'] for t in techs[:10])}")

    concepts = result.get("concepts", [])
    if concepts:
        lines.append(f"涵蓋概念（共 {len(concepts)} 個）：{', '.join(c['name'] for c in concepts[:15])}")
        if len(concepts) > 15:
            lines.append(f"  ...等 {len(concepts)} 個概念")

    similar = result.get("similar_courses", [])
    if similar:
        lines.append(f"\n概念重疊最高的相關課程（可延伸學習）：")
        for s in similar[:8]:
            lines.append(f"  - {s['name']}（{s['dept']}）[共享 {s.get('shared_concepts', 0)} 個概念]")

    return "\n".join(lines)


def tool_get_depts_by_tech(tech_name: str) -> str:
    """Multi-hop 查詢哪些系所的課程有教某技術或概念。

    【使用時機】使用者問「什麼科系需要學 Python？」「哪些系有教機器學習？」
    「哪個系所最重視 SQL 技術？」等問題時使用。
    利用知識圖譜的多跳路徑，區分「必修」與「選修」含此技術的系所。
    比向量搜尋更能呈現結構性的「哪些系重視這個技術」。
    """
    result = graph_service.get_depts_by_tech(tech_name)
    if not result["courses"]:
        return f"知識圖譜中找不到教「{tech_name}」的課程（請嘗試英文或其他名稱）。"

    lines = [f"教「{tech_name}」的系所分布（共 {len(result['courses'])} 門相關課程）："]

    req = result.get("required_depts", [])
    if req:
        lines.append(f"\n必修課含此技術的系所（{len(req)} 個）：")
        for d in req[:12]:
            lines.append(f"  - {d}")

    elec = result.get("elective_depts", [])
    if elec:
        lines.append(f"\n選修課含此技術的系所（{len(elec)} 個）：")
        for d in elec[:12]:
            lines.append(f"  - {d}")

    lines.append(f"\n相關課程（前 10 門）：")
    for c in result["courses"][:10]:
        lines.append(f"  - {c['name']}（{c.get('dept', '')}）")

    return "\n".join(lines)


def tool_ppr_explore(
    seed: str,
    focus: str = "all",
    top_k: int = 15,
) -> str:
    """Personalized PageRank 探索：從種子概念出發，找整個知識圖譜中最相關的節點。

    【使用時機】使用者想做廣泛探索時：
    - 「和機器學習相關的一切有哪些？」
    - 「我對 AI 有興趣，中央大學有什麼相關資源？」
    - 「深度學習連結到哪些老師和系所？」
    比 find_similar_courses 更廣，能跨越課程、老師、系所、概念等所有節點類型。

    focus 參數：
    - "all"：回傳所有節點類型
    - "course"：只回傳課程
    - "instructor"：只回傳教師
    - "dept"：只回傳系所
    - "concept"：只回傳概念/技術節點
    """
    focus_map = {
        "course":     ["Course"],
        "instructor": ["Instructor"],
        "dept":       ["Department", "DeptGroup", "CollegeBachelorProgram"],
        "concept":    ["Concept", "Technology", "Field"],
    }
    type_filter = focus_map.get(focus)
    seed_list = [s.strip() for s in seed.replace("、", ",").replace("，", ",").split(",")]

    results = graph_service.ppr_explore(
        seed_names=seed_list,
        top_k=top_k,
        node_type_filter=type_filter,
    )

    if not results:
        return f"找不到以「{seed}」為起點的相關節點（請確認概念名稱是否正確）。"

    lines = [f"以「{seed}」為起點的 PPR 探索結果（{focus} 模式）："]
    type_labels = {
        "Course": "課程", "Instructor": "教師",
        "Department": "系所", "DeptGroup": "系所分組",
        "CollegeBachelorProgram": "學院學士班",
        "Concept": "概念", "Technology": "技術", "Field": "研究領域",
        "CreditProgram": "學分學程",
    }
    for r in results:
        label = type_labels.get(r["node_type"], r["node_type"])
        name = r["name"]
        extra = ""
        if r.get("dept"):
            extra = f"（{r['dept']}）"
        score = r.get("score", 0)
        lines.append(f"  [{label}] {name}{extra}  [PPR: {score}]")

    return "\n".join(lines)


def tool_get_program_description(program_name: str) -> str:
    """直接從 program_descriptions.json 取得學分學程的完整說明。

    【使用時機】使用者詢問某學分學程的說明、目標、修課方式、學程內容時，
    此工具比向量搜尋更完整，應優先使用。
    若想同時取得課程清單，可搭配 get_program_courses 一起呼叫。
    """
    data = _load_program_descriptions()
    if not data:
        return "program_descriptions.json 資料尚未載入。"
    # 精確 / 包含比對
    for name, desc in data.items():
        if program_name in name or name in program_name:
            return f"【{name}】\n{desc}"
    # 部分字元模糊比對（任一字元命中）
    matches = [(k, v) for k, v in data.items()
               if any(c in k for c in program_name if len(c.encode()) > 1)]
    if matches:
        return "\n\n".join(f"【{k}】\n{v}" for k, v in matches[:3])
    return "找不到符合的學程說明。現有學程：\n" + "\n".join(f"- {k}" for k in data.keys())


def tool_get_requirements_notes(dept_name: str) -> str:
    """直接從 requirements_notes.json 取得系所畢業規定原文。

    【使用時機】使用者詢問某系所畢業學分、修課規定、必選修要求、
    修業規定細節時，此工具比 get_graduation_rules 更完整（含原始說明文字），
    應優先使用。
    """
    data = _load_requirements_notes()
    if not data:
        return "requirements_notes.json 資料尚未載入。"
    for dept, notes in data.items():
        if dept_name in dept or dept in dept_name:
            return f"【{dept} 畢業規定】\n{notes}"
    # 模糊
    matches = [(k, v) for k, v in data.items()
               if any(c in k for c in dept_name if len(c.encode()) > 1)]
    if matches:
        return "\n\n".join(f"【{k}】\n{v}" for k, v in matches[:2])
    return f"找不到「{dept_name}」的畢業規定資料。"


def tool_find_similar_courses(course_name: str) -> str:
    """找與指定課程有最多共同概念的相似課程（跨系所）。

    【使用時機】使用者問「有沒有類似 OO 的課？」、「哪些課和 OO 有關？」、
    「跨系有沒有教類似內容的課？」時使用。
    利用知識圖譜的 Concept/Technology 節點做語意擴散，覆蓋比關鍵字搜尋更廣。
    """
    results = graph_service.search_courses_by_concept_cluster(course_name, top_n=15)
    if not results:
        return (f"找不到與「{course_name}」概念相近的課程（可能課程名稱不符，"
                f"請嘗試更短的關鍵詞，如只輸入核心詞）。")
    lines = [f"與「{course_name}」概念相近的課程（共 {len(results)} 門）："]
    for r in results:
        line = f"- {r['name']}（{r['dept']}，{r.get('credits', '?')}學分）"
        cnt = r.get("shared_concepts", 0)
        if cnt > 1:
            line += f" [共享概念：{cnt} 個]"
        lines.append(line)
    return "\n".join(lines)


def tool_get_graduation_requirements(dept_name: str) -> dict:
    """查詢系所畢業規定：結構化學分要求（最低學分、必修學分、認證要求）+ 完整原文。

    整合原有 get_graduation_rules 與 get_requirements_notes，一次呼叫取得全部。
    """
    rules = graph_service.get_graduation_rules(dept_name)
    notes_data = _load_requirements_notes()

    raw_notes = ""
    for dept, notes in notes_data.items():
        if dept_name in dept or dept in dept_name:
            raw_notes = notes
            break
    if not raw_notes:
        for dept, notes in notes_data.items():
            if any(c in dept for c in dept_name if len(c.encode()) > 1):
                raw_notes = notes
                break

    if not rules and not raw_notes:
        return {"found": False, "message": f"找不到「{dept_name}」的畢業規定資料"}

    result: dict = {"found": True, "dept_name": dept_name, "raw_notes": raw_notes}
    if rules:
        result["min_credits"]      = rules.get("min_credits")
        result["required_credits"] = rules.get("required_credits")
        result["certifications"]   = rules.get("certifications", [])
    return result


def tool_search_programs(query: str, n: int = 5) -> list[dict]:
    """語意搜尋學分學程，依描述或主題找最相關的學程清單。

    【使用時機】使用者問「有沒有 AI 相關的學程？」「理工學院有哪些學程？」等發現型查詢。
    找到學程後，再用 get_program_description / get_program_courses 取得詳情。
    """
    results = retriever.search_programs(query, n_results=n)
    return [
        {
            "program_name":        r.get("metadata", {}).get("program_name", ""),
            "college":             r.get("metadata", {}).get("college", ""),
            "description_excerpt": r.get("document", "")[:300],
            "distance":            round(r.get("distance", 0.0), 4),
        }
        for r in results
    ]


def tool_get_course_syllabus(
    name_zh: str = None,
    dept: str = None,
    course_code: str = None,
) -> dict:
    """查詢課程的官方課綱：課程目標、授課內容、教科書/參考書。

    【使用時機】使用者問「演算法在學什麼？」「這門課用什麼教科書？」等需要官方說明的問題。
    與 get_course_knowledge_map 互補（後者是 NLP 提取的概念圖）。

    同名課程消歧義：
    - 有 course_code → 精確查詢，無歧義
    - 只有 name_zh → 若多科系都有此課，回傳 ambiguous=True + candidates，由使用者選擇
    - name_zh + dept → 精確定位到指定科系
    """
    if course_code:
        results = retriever.get_courses_by_code(course_code)
        if not results:
            results = retriever.get_courses_by_code(course_code, collection="ncu_courses_grad")
        if not results:
            return {"found": False, "message": f"找不到課號「{course_code}」"}
        m = results[0]["metadata"]
        return {
            "found": True, "ambiguous": False,
            "course_code": m.get("course_code", ""),
            "name_zh":     m.get("name_zh", ""),
            "dept":        m.get("dept", ""),
            "teacher":     m.get("teacher", ""),
            "credits":     m.get("credits", 0),
            "objective":   m.get("objective", ""),
            "content":     m.get("content", ""),
            "textbook":    m.get("textbook", ""),
        }

    if not name_zh:
        return {"found": False, "message": "請提供課程名稱（name_zh）或課號（course_code）"}

    exact = retriever.get_courses_by_name(name_zh)
    if not exact:
        return {"found": False, "message": f"找不到課程「{name_zh}」"}

    if dept:
        filtered = [r for r in exact if r["metadata"].get("dept", "") == dept]
        if filtered:
            exact = filtered

    depts = list({r["metadata"].get("dept", "") for r in exact})
    if len(depts) > 1 and not dept:
        return {
            "found": True,
            "ambiguous": True,
            "message": f"找到 {len(depts)} 個科系都有「{name_zh}」，請指定 dept 或由使用者選擇：",
            "candidates": [
                {
                    "dept":        r["metadata"].get("dept", ""),
                    "course_code": r["metadata"].get("course_code", ""),
                    "teacher":     r["metadata"].get("teacher", ""),
                    "credits":     r["metadata"].get("credits", 0),
                }
                for r in exact
            ],
        }

    m = exact[0]["metadata"]
    return {
        "found": True, "ambiguous": False,
        "course_code": m.get("course_code", ""),
        "name_zh":     m.get("name_zh", ""),
        "dept":        m.get("dept", ""),
        "teacher":     m.get("teacher", ""),
        "credits":     m.get("credits", 0),
        "objective":   m.get("objective", ""),
        "content":     m.get("content", ""),
        "textbook":    m.get("textbook", ""),
    }


# ── 分派表 ────────────────────────────────────────────────────────────────────

_TOOL_MAP = {
    "search_courses":              tool_search_courses,
    "get_dept_courses":            tool_get_dept_courses,
    "get_program_courses":         tool_get_program_courses,
    "get_teacher_info":            tool_get_teacher_info,
    "search_teachers":             tool_search_teachers,
    "get_prereq_info":             tool_get_prereq_info,
    "get_graduation_requirements": tool_get_graduation_requirements,
    "get_graduation_rules":        tool_get_graduation_rules,       # backward compat
    "get_requirements_notes":      tool_get_requirements_notes,     # backward compat
    "get_dept_info":               tool_get_dept_info,
    "get_course_eligibility":      tool_get_course_eligibility,
    "get_program_description":     tool_get_program_description,
    "search_programs":             tool_search_programs,
    "find_similar_courses":        tool_find_similar_courses,
    "get_course_knowledge_map":    tool_get_course_knowledge_map,
    "get_depts_by_tech":           tool_get_depts_by_tech,
    "ppr_explore":                 tool_ppr_explore,
    "get_course_syllabus":         tool_get_course_syllabus,
}


def execute_tool(name: str, args: dict):
    fn = _TOOL_MAP.get(name)
    if fn is None:
        return {"error": f"未知工具：{name}"}
    # Filter out unknown kwargs — LLM sometimes hallucinates parameter names (e.g. 'eligable_year')
    valid_params = set(inspect.signature(fn).parameters.keys())
    filtered_args = {k: v for k, v in args.items() if k in valid_params}
    try:
        return fn(**filtered_args)
    except Exception as e:
        return {"error": str(e)}


# ── OpenAI Function Schema ────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "語意搜尋課程，支援依系所、學院、技術、年級、學期、選修別、修課資格等條件過濾。【重要】當使用者詢問特定程式語言或工具（如 PyTorch、Python、TensorFlow、Pandas、MATLAB 等），必須使用 tech 參數進行精確過濾，不可只靠語意搜尋。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":        {"type": "string",  "description": "搜尋關鍵詞或自然語言描述（必填）"},
                    "dept":         {"type": "string",  "description": "限縮系所，如「資訊工程學系」"},
                    "college":      {"type": "string",  "description": "限縮學院，如「資訊電機學院」"},
                    "course_type":  {"type": "string",  "enum": ["必修", "選修"], "description": "課程性質"},
                    "year":         {"type": "integer", "description": "建議修習年級（1-4）"},
                    "sem":          {"type": "integer", "enum": [1, 2], "description": "1=上學期，2=下學期"},
                    "tech":              {"type": "string",  "description": "技術或工具名稱，如「PyTorch」「Python」"},
                    "is_grad":           {"type": "boolean", "description": "true=搜尋研究所課程"},
                    "exclude_grad_only": {"type": "boolean", "description": "true（預設）=排除限研究所才能修的課程；false=顯示全部"},
                    "n":                 {"type": "integer", "description": "回傳筆數（預設 8）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dept_courses",
            "description": "從知識圖譜查詢某系所的必修或選修課程（結構化資料，比向量搜尋更精確）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dept_name":   {"type": "string", "description": "系所名稱，如「資訊工程學系」"},
                    "course_type": {"type": "string", "enum": ["required", "elective", "all"],
                                   "description": "required=必修，elective=選修，all=全部（預設 required）"},
                },
                "required": ["dept_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_program_courses",
            "description": "查詢學分學程的必修和選修課程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_name": {"type": "string", "description": "學程名稱，如「人工智慧技術應用」"},
                },
                "required": ["program_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_teacher_info",
            "description": "查詢特定教師的官方專長（教育部申報）與開課清單。",
            "parameters": {
                "type": "object",
                "properties": {
                    "teacher_name": {"type": "string", "description": "教師姓名"},
                },
                "required": ["teacher_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_teachers",
            "description": "依研究領域或專長關鍵詞語意搜尋教師，適合「哪位教授專長是 NLP」此類查詢。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",  "description": "研究領域或專長描述"},
                    "n":     {"type": "integer", "description": "回傳筆數（預設 5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prereq_info",
            "description": "查詢課程的先修要求，並回傳先修課程的詳細資訊（課名、學分、建議修習學期）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_query": {"type": "string", "description": "課程名稱或課號"},
                },
                "required": ["course_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_graduation_requirements",
            "description": "查詢某系所的畢業規定：同時回傳結構化學分要求（最低學分、必修學分、認證要求清單）與完整原文說明。整合原有兩個工具，一次呼叫即可。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dept_name": {"type": "string", "description": "系所名稱，如「資訊工程學系」「大氣科學學系」"},
                },
                "required": ["dept_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dept_info",
            "description": "查詢系所介紹、學系特色、生涯進路、能力特質（來自 Collego 資料）。適合「XX系在學什麼」、「適合什麼人」此類查詢。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "系所名稱或描述，如「適合喜歡設計的人的系所」"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_program_description",
            "description": "直接取得學分學程的完整說明文字（目標、修課方式、學程特色）。【優先使用】比向量搜尋更完整，詢問學程說明時請優先呼叫此工具，可搭配 get_program_courses 同時取得課程清單。",
            "parameters": {
                "type": "object",
                "properties": {
                    "program_name": {"type": "string", "description": "學程名稱，如「人工智慧技術應用」「資訊安全」"},
                },
                "required": ["program_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_eligibility",
            "description": "查詢課程修課資格限制：適合年級、限定系所、是否開放外系/輔系/雙主修等。回傳原始分發條件原文（raw_conditions），有多門同名課程時全部回傳。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_query": {"type": "string", "description": "課程名稱或課號"},
                },
                "required": ["course_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_programs",
            "description": "語意搜尋學分學程，依描述、主題或學院找最相關的學程清單。適合「有沒有 AI 相關的學程？」「管理學院有哪些學程？」等發現型查詢。找到後可用 get_program_description / get_program_courses 取得詳情。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "學程主題或描述，如「人工智慧」「語言文化」「永續環境」"},
                    "n":     {"type": "integer", "description": "回傳筆數（預設 5）"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_syllabus",
            "description": "查詢課程官方課綱：課程目標、授課內容、教科書/參考書。與 get_course_knowledge_map 互補（後者是 NLP 提取的概念圖，此工具是官方說明）。同名課程會回傳 ambiguous=True + candidates 供選擇；可用 course_code 精確查詢。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_zh":     {"type": "string",  "description": "課程中文名稱，如「演算法」「普通化學」"},
                    "dept":        {"type": "string",  "description": "指定系所以消歧義，如「化學學系」"},
                    "course_code": {"type": "string",  "description": "課號，精確查詢無歧義，優先使用"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_courses",
            "description": "透過知識圖譜 Concept 節點找與指定課程概念最相近的跨系課程。適合「有沒有類似 OO 的課」、「跨系有沒有教 OO 的課」等推薦類查詢。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {"type": "string", "description": "課程名稱，如「機器學習」「演算法」"},
                },
                "required": ["course_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_knowledge_map",
            "description": "回傳一門課的知識地圖：它涵蓋的學術概念、使用的技術工具，以及概念重疊最高的跨系相似課程。適合「演算法在教什麼？」「機器學習和哪些課最像？」等探索式問題。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {"type": "string", "description": "課程名稱，如「演算法」「機器學習」「深度學習」"},
                },
                "required": ["course_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_depts_by_tech",
            "description": "多跳圖查詢：哪些系所的課程有教某技術或概念？區分必修與選修。適合「什麼科系需要學 Python？」「哪些系重視機器學習？」等問題。",
            "parameters": {
                "type": "object",
                "properties": {
                    "tech_name": {"type": "string", "description": "技術或概念名稱，如「Python」「機器學習」「SQL」"},
                },
                "required": ["tech_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ppr_explore",
            "description": "Personalized PageRank 廣泛探索：從概念/課程出發，找知識圖譜中最相關的節點（可跨課程、教師、系所、概念）。適合「和 AI 相關的一切有哪些？」「深度學習連結到哪些老師和系所？」等廣泛探索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "seed":  {"type": "string", "description": "起始概念或課程名稱，可用逗號分隔多個，如「機器學習」或「機器學習,深度學習」"},
                    "focus": {"type": "string", "enum": ["all", "course", "instructor", "dept", "concept"],
                              "description": "回傳節點類型：all=全部，course=課程，instructor=教師，dept=系所，concept=概念技術"},
                    "top_k": {"type": "integer", "description": "回傳數量（預設 15）"},
                },
                "required": ["seed"],
            },
        },
    },
]
