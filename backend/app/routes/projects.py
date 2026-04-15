from fastapi import APIRouter, Query
from typing import List, Optional
import json
import os
from urllib.parse import quote
from app.models.schemas import Project, ChatRequest, ChatResponse

router = APIRouter()

# 載入大專生計畫資料
def load_projects():
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'processed', 'projects.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        projects = json.load(f)

    for project in projects:
        pdf_path = project.get('pdfPath')
        if pdf_path:
            project['pdfUrl'] = build_pdf_url(pdf_path)

    return projects


def build_pdf_url(pdf_path: str) -> str:
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    project_folder = os.getenv("CLOUDINARY_PROJECT_FOLDER")

    if cloud_name and project_folder:
        encoded_parts = [quote(part, safe="") for part in pdf_path.split("\\")]
        encoded_path = "/".join(encoded_parts)
        encoded_folder = "/".join(quote(part, safe="") for part in project_folder.strip("/").split("/"))
        return f"https://res.cloudinary.com/{cloud_name}/raw/upload/{encoded_folder}/{encoded_path}"

    encoded_path = "/".join(quote(part, safe="") for part in pdf_path.split("\\"))
    return f"/pdfs/{encoded_path}"

@router.get("", response_model=List[Project])
async def get_projects(
    department: Optional[str] = Query(None, description="科系篩選"),
    year: Optional[str] = Query(None, description="學年度篩選")
):
    """
    取得大專生計畫列表
    """
    projects = load_projects()

    # 套用篩選條件
    filtered_projects = projects

    if department:
        filtered_projects = [p for p in filtered_projects if p['department'] == department]

    if year:
        filtered_projects = [p for p in filtered_projects if p['year'] == year]

    return filtered_projects

@router.get("/{project_id}", response_model=Project)
async def get_project_by_id(project_id: str):
    """
    取得單一大專生計畫詳情
    """
    projects = load_projects()

    for project in projects:
        if project['id'] == project_id:
            return project

    return {"error": "Project not found"}

@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat_with_project(project_id: str, request: ChatRequest):
    """
    與大專生計畫 PDF 對話（Mock 版本）
    """
    # TODO: 後續整合真實的 RAG 功能
    # 目前回傳模擬回覆

    mock_replies = [
        f"這是關於計畫 {project_id} 的回覆。您的問題是：{request.message}",
        "根據這份研究計畫，主要探討的是...",
        "這個計畫的研究方法包括...",
        "研究結果顯示...",
    ]

    import random
    reply = random.choice(mock_replies)

    return ChatResponse(reply=reply)
