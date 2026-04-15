"""
course_classifier.py  —  課程分類共用模組

classify_course(course) → 'SKIP' | 'SEQUENCE_ONLY' | 'TOPICS_ONLY' | 'FULL'

分類邏輯（優先順序由高到低）：
  1. 已停開（課程名稱含「已停開」）→ SKIP
  2. 三欄皆空（目標+內容+教科書全空）→ SKIP
  3. 系所名稱含特定關鍵字 → SKIP / SEQUENCE_ONLY / TOPICS_ONLY
  4. 其餘 → FULL
"""

# ── 以「系所名稱」判斷 ────────────────────────────────────────
DEPT_SKIP_KW          = ["體育", "軍訓"]
DEPT_SEQUENCE_ONLY_KW = ["語言中心", "服務學習", "職涯"]
DEPT_TOPICS_ONLY_KW   = ["通識", "核心通識"]


def classify_course(course: dict) -> str:
    """
    輸入：原始課程 dict（來自 JSON）
    輸出：'SKIP' | 'SEQUENCE_ONLY' | 'TOPICS_ONLY' | 'FULL'
    """
    name = course.get("課程名稱(中文)", "")
    dept = course.get("系所", course.get("department", ""))
    outline = course.get("課程綱要", {}) or {}
    objective = (outline.get("課程目標", "") or course.get("課程目標", "") or "").strip()
    content   = (outline.get("授課內容", "") or course.get("授課內容", "") or "").strip()
    books     = (outline.get("教科書/參考書", "") or course.get("教科書/參考書", "") or "").strip()

    # 1. 三欄皆空（無內容可給 LLM）
    if not objective and not content and not books:
        return "SKIP"

    # 3. 系所關鍵字
    if any(kw in dept for kw in DEPT_SKIP_KW):
        return "SKIP"
    if any(kw in dept for kw in DEPT_SEQUENCE_ONLY_KW):
        return "SEQUENCE_ONLY"
    if any(kw in dept for kw in DEPT_TOPICS_ONLY_KW):
        return "TOPICS_ONLY"

    return "FULL"
