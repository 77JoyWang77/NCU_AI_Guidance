"""
intent_classifier.py

輕量意圖分類，優先用 Regex，輔以關鍵詞清單。
回傳結構：{"intent": str, "entities": dict}

Intent 清單：
  semantic      — 課程語意搜尋（預設）
  tech_filter   — 技術/工具找課（「教 PyTorch 的課」）
  dept_required — 系所必修查詢
  dept_elective — 系所選修查詢
  program       — 學分學程查詢
  schedule      — 年次修課規劃（大一、大二…）
  teacher       — 教師查詢（找老師 or 找老師的課）
  department    — 系所介紹查詢
  grad          — 研究所課程搜尋
"""

import re
from typing import Any

# ── Regex patterns ────────────────────────────────────────────────────────────

_YEAR_MAP = {"大一": 1, "大二": 2, "大三": 3, "大四": 4,
             "一年級": 1, "二年級": 2, "三年級": 3, "四年級": 4}
_SEM_MAP = {"上學期": 1, "下學期": 2, "上": 1, "下": 2}

_TECH_PATTERNS = [
    r"教\s*(.+?)\s*的課",
    r"學\s*(.+?)\s*的課",
    r"有.*?(.+?)\s*的課程",
    r"哪些課.*?(會教|有教|使用|涵蓋)\s*(.+)",
    r"(.+?)\s*相關的課",
]

_TEACHER_PATTERNS = [
    r"(.{2,5})\s*(教授|老師|博士)\s*教",
    r"(.{2,5})\s*(教授|老師|博士)\s*的課",
    r"(.{2,5})\s*(教授|老師|博士)\s*研究",
    r"哪位.*?(教授|老師|博士).*?專長",
    r"找.*?(教授|老師|博士).*?專長",
    r"誰.*?教\s*(.+)",
]

_DEPT_REQ_KEYWORDS = ["必修", "必修科目", "系必修", "系訂必修", "共同必修"]
_DEPT_ELV_KEYWORDS = ["選修", "系選修", "開授"]
_PROGRAM_KEYWORDS = ["學分學程", "學程", "學分程"]
_DEPT_INTRO_KEYWORDS = ["介紹", "特色", "適合", "在學什麼", "生涯", "出路", "進路",
                         "學什麼", "讀什麼"]
_GRAD_KEYWORDS = ["研究所", "碩士", "博士", "研所", "graduate"]
_GRADUATION_KEYWORDS = ["畢業學分", "幾學分畢業", "修業規定", "畢業規定", "畢業要求", "最低學分", "畢業條件"]
_PREREQ_KEYWORDS = ["先修", "前置課程", "要先修", "先要修", "修過才能", "修完才能", "prerequisite"]
_ELIGIBILITY_KEYWORDS = ["可以修嗎", "能修嗎", "修課資格", "幾年級能修", "哪些人能修", "限修", "有資格修"]


def classify(query: str) -> dict[str, Any]:
    q = query.strip()
    entities: dict[str, Any] = {}

    # ── 研究所 ──
    if any(kw in q for kw in _GRAD_KEYWORDS):
        return {"intent": "grad", "entities": entities}

    # ── 畢業規定 ──
    if any(kw in q for kw in _GRADUATION_KEYWORDS):
        dept_m = re.search(r"([^\s，。？、]{2,10}(?:學系|系|所|學院))", q)
        if dept_m:
            entities["dept_name"] = dept_m.group(1)
        return {"intent": "graduation_rules", "entities": entities}

    # ── 先修查詢 ──
    if any(kw in q for kw in _PREREQ_KEYWORDS):
        return {"intent": "prereq", "entities": entities}

    # ── 修課資格 ──
    if any(kw in q for kw in _ELIGIBILITY_KEYWORDS):
        for text, year in _YEAR_MAP.items():
            if text in q:
                entities["year"] = year
                break
        return {"intent": "eligibility", "entities": entities}

    # ── 教師相關 ──
    for pat in _TEACHER_PATTERNS:
        m = re.search(pat, q)
        if m:
            # 如果問的是「哪位…專長」→ teacher_search
            if "哪位" in q or "誰" in q:
                return {"intent": "teacher", "entities": {"mode": "search"}}
            # 否則是特定教師查詢
            name = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
            if name and not any(kw in name for kw in ["哪", "什麼", "誰"]):
                entities["teacher_name"] = name.strip()
                return {"intent": "teacher", "entities": entities}

    # ── 年次修課 ──
    for text, year in _YEAR_MAP.items():
        if text in q:
            entities["year"] = year
            for sem_text, sem in _SEM_MAP.items():
                if sem_text in q:
                    entities["sem"] = sem
                    break
            # 有「必修」→ 更細化
            if any(kw in q for kw in _DEPT_REQ_KEYWORDS):
                entities["type"] = "必修"
            return {"intent": "schedule", "entities": entities}

    # ── 學分學程 ──
    if any(kw in q for kw in _PROGRAM_KEYWORDS):
        # 提取學程名稱
        m = re.search(r"「?(.{3,20}?學程)」?", q)
        if m:
            entities["program_name"] = m.group(1)
        return {"intent": "program", "entities": entities}

    # ── 系所必修/選修 ──
    has_req = any(kw in q for kw in _DEPT_REQ_KEYWORDS)
    has_elv = any(kw in q for kw in _DEPT_ELV_KEYWORDS)
    # 提取系所名稱
    dept_match = re.search(r"([^\s，。？、]{2,10}(?:學系|學院|系所|研究所|學士班))", q)
    if dept_match:
        entities["dept_name"] = dept_match.group(1)
    if has_req:
        return {"intent": "dept_required", "entities": entities}
    if has_elv and dept_match:
        return {"intent": "dept_elective", "entities": entities}

    # ── 技術/工具找課 ──
    for pat in _TECH_PATTERNS:
        m = re.search(pat, q)
        if m:
            tech = m.group(m.lastindex or 1).strip()
            if tech and len(tech) <= 30:
                entities["tech"] = tech
                return {"intent": "tech_filter", "entities": entities}

    # ── 系所介紹 ──
    if any(kw in q for kw in _DEPT_INTRO_KEYWORDS):
        dept_match2 = re.search(r"([^\s，。？、]{2,10}(?:系|所|院|學部))", q)
        if dept_match2:
            entities["dept_name"] = dept_match2.group(1)
        return {"intent": "department", "entities": entities}

    # ── 預設：語意搜尋 ──
    return {"intent": "semantic", "entities": entities}
