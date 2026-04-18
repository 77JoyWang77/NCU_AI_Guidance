"""
tools.py

ReAct Tool-Use 工具定義與執行器。
每個 tool_* 函式對應一個 OpenAI function schema，
execute_tool() 依工具名稱分派執行。
"""

from app.services import retriever, graph_service


# ── 結果格式化 ────────────────────────────────────────────────────────────────

def _fmt_courses(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        m = r.get("metadata", {})
        out.append({
            "course_code":        m.get("course_code", ""),
            "name_zh":            m.get("name_zh", ""),
            "name_en":            m.get("name_en", ""),
            "dept":               m.get("dept", ""),
            "college":            m.get("college", ""),
            "credits":            m.get("credits", 0),
            "type":               m.get("type", ""),
            "teacher":            m.get("teacher", ""),
            "teacher_specialties":m.get("teacher_specialties", ""),
            "when_raw":           m.get("when_raw", ""),
            "prereq_codes":       m.get("prereq_codes", ""),
            "eligible_years":     m.get("eligible_years", ""),
            "languages":          m.get("languages", ""),
            "tools":              m.get("tools", ""),
            "domain_tags":        m.get("domain_tags", ""),
            "summary":            r.get("document", "")[:200],
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
    eligible_year: int = None,
    n: int = 8,
) -> list[dict]:
    """語意搜尋課程，組裝 ChromaDB filters 後呼叫 retriever。"""
    filters: dict = {}
    if dept:
        filters["dept"] = dept
    if college:
        filters["college"] = college
    if course_type:
        filters["type"] = course_type
    if tech:
        filters["$or"] = [
            {"tools":     {"$contains": tech}},
            {"languages": {"$contains": tech}},
            {"concepts":  {"$contains": tech}},
        ]
    if year is not None and sem is not None:
        filters["when_semesters"] = {"$contains": f"{year}_{sem}"}
    elif year is not None:
        filters["$or"] = [
            {"when_semesters": {"$contains": f"{year}_1"}},
            {"when_semesters": {"$contains": f"{year}_2"}},
        ]
    if eligible_year is not None:
        filters["eligible_years"] = {"$contains": str(eligible_year)}

    collection = "ncu_courses_grad" if is_grad else "ncu_courses_ug"
    results = retriever.search_courses(
        query, filters=filters or None, n_results=n, collection=collection
    )
    return _fmt_courses(results)


def tool_get_dept_courses(dept_name: str, course_type: str = "required") -> dict:
    """圖查詢系所必修或選修課程。"""
    if course_type == "required":
        courses = graph_service.get_dept_required_courses(dept_name)
    elif course_type == "elective":
        courses = graph_service.get_dept_elective_courses(dept_name)
    else:
        courses = (
            graph_service.get_dept_required_courses(dept_name) +
            graph_service.get_dept_elective_courses(dept_name)
        )
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


def tool_get_course_eligibility(course_query: str) -> dict:
    """查詢課程的修課資格限制（年級、系所、是否開放外系等）。"""
    results = retriever.search_courses(course_query, n_results=3)
    if not results:
        return {"found": False, "message": f"找不到「{course_query}」"}
    m = results[0].get("metadata", {})
    return {
        "course_code":          m.get("course_code", ""),
        "name_zh":              m.get("name_zh", ""),
        "eligible_years":       m.get("eligible_years", ""),
        "dept_include":         m.get("dept_include", ""),
        "college_include":      m.get("college_include", ""),
        "open_to_minor":        m.get("open_to_minor", False),
        "open_to_double_major": m.get("open_to_double_major", False),
        "open_to_credit_prog":  m.get("open_to_credit_prog", False),
        "open_to_cross_school": m.get("open_to_cross_school", False),
        "is_unrestricted":      m.get("is_unrestricted", False),
        "has_special_condition":m.get("has_special_condition", False),
    }


# ── 分派表 ────────────────────────────────────────────────────────────────────

_TOOL_MAP = {
    "search_courses":          tool_search_courses,
    "get_dept_courses":        tool_get_dept_courses,
    "get_program_courses":     tool_get_program_courses,
    "get_teacher_info":        tool_get_teacher_info,
    "search_teachers":         tool_search_teachers,
    "get_prereq_info":         tool_get_prereq_info,
    "get_graduation_rules":    tool_get_graduation_rules,
    "get_dept_info":           tool_get_dept_info,
    "get_course_eligibility":  tool_get_course_eligibility,
}


def execute_tool(name: str, args: dict):
    fn = _TOOL_MAP.get(name)
    if fn is None:
        return {"error": f"未知工具：{name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}


# ── OpenAI Function Schema ────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "語意搜尋課程，支援依系所、學院、技術、年級、學期、選修別、修課資格等條件過濾。適用於大多數課程查詢。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":        {"type": "string",  "description": "搜尋關鍵詞或自然語言描述（必填）"},
                    "dept":         {"type": "string",  "description": "限縮系所，如「資訊工程學系」"},
                    "college":      {"type": "string",  "description": "限縮學院，如「資訊電機學院」"},
                    "course_type":  {"type": "string",  "enum": ["必修", "選修"], "description": "課程性質"},
                    "year":         {"type": "integer", "description": "建議修習年級（1-4）"},
                    "sem":          {"type": "integer", "enum": [1, 2], "description": "1=上學期，2=下學期"},
                    "tech":         {"type": "string",  "description": "技術或工具名稱，如「PyTorch」「Python」"},
                    "is_grad":      {"type": "boolean", "description": "true=搜尋研究所課程"},
                    "eligible_year":{"type": "integer", "description": "幾年級才可修（修課資格過濾）"},
                    "n":            {"type": "integer", "description": "回傳筆數（預設 8）"},
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
            "name": "get_graduation_rules",
            "description": "查詢某系所的畢業學分要求、必修學分、畢業規定條文與認證要求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dept_name": {"type": "string", "description": "系所名稱"},
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
            "name": "get_course_eligibility",
            "description": "查詢某課程的修課資格限制：適合年級、限定系所、是否開放外系、輔系、雙主修等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_query": {"type": "string", "description": "課程名稱或課號"},
                },
                "required": ["course_query"],
            },
        },
    },
]
