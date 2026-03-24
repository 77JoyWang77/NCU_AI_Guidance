from fastapi import APIRouter
from typing import List
import json
import os
from app.models.schemas import Course, CourseSearchRequest

router = APIRouter()

# 載入課程資料
def load_courses():
    # 從 data/processed 載入課程資料
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'processed', 'courses.json')

    courses = []
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    course = json.loads(line)
                    courses.append(course)
                except json.JSONDecodeError:
                    continue
    return courses

@router.post("", response_model=List[Course])
async def search_courses(request: CourseSearchRequest):
    """
    使用關鍵字搜尋課程（簡單版本，不使用 RAG）
    """
    query = request.query.lower()
    courses = load_courses()

    # 簡單關鍵字比對
    matched_courses = []

    for course in courses:
        # 搜尋課程名稱、系所、課程綱要
        course_name = course.get('课程名称中文', '').lower()
        course_name_en = course.get('课程名称英文', '').lower()
        department = course.get('系所', '').lower()
        college = course.get('学院', '').lower()

        # 搜尋課程綱要
        outline = course.get('课程纲要', {})
        content = ''
        if outline:
            content = (
                outline.get('课程目标', '') +
                outline.get('课程内容', '') +
                outline.get('教科书', '')
            ).lower()

        # 若查詢詞出現在任何欄位中則比對
        if (query in course_name or
            query in course_name_en or
            query in department or
            query in college or
            query in content):
            matched_courses.append(course)

        # 限制回傳結果數量
        if len(matched_courses) >= 50:
            break

    return matched_courses
