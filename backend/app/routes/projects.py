from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json
import json as _json
import os
from urllib.parse import quote
from app.models.schemas import Project, ChatRequest, ChatResponse
from app.services.auth_service import get_optional_user, AuthUser
from app.agents.pdf.router_agent import route_agent_stream
from app.agents.pdf import chat_jobs, steering
from app.agents.pdf.request_context import set_user_id
from app.services.pdf_llm_gate import get_gate
from app.database_pdf import PdfSessionLocal
from app.models.pdf_models import PdfDocument, PdfConversation
from app.utils import new_id

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
        encoded_parts = [quote(part.replace("&", "and"), safe="") for part in pdf_path.split("\\")]
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

# ── 輔助函式 ──────────────────────────────────────────────────

def _get_document_ids_for_project(project_id: str) -> list[int]:
    """project_id → pdf_documents.id（比對 pdfPath 檔名）。"""
    projects = load_projects()
    project = next((p for p in projects if p["id"] == project_id), None)
    if not project or not project.get("pdfPath"):
        return []
    filename = project["pdfPath"].replace("\\", "/").split("/")[-1]
    with PdfSessionLocal() as db:
        doc = db.query(PdfDocument.id).filter(
            PdfDocument.filename.ilike(f"%{filename}%"),
            PdfDocument.status == "ready",
        ).first()
    return [doc.id] if doc else []


def _get_or_create_pdf_conversation(thread_id: str, user_id: str | None) -> PdfConversation:
    with PdfSessionLocal() as db:
        conv = db.query(PdfConversation).filter_by(thread_id=thread_id).first()
        if not conv:
            conv = PdfConversation(thread_id=thread_id, user_id=user_id)
            db.add(conv)
            db.commit()
            db.refresh(conv)
    return conv


def _is_within_ttl(stream_started_at, ttl_seconds: int = 30) -> bool:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    started = stream_started_at
    if started.tzinfo is None:
        from datetime import timezone as _tz
        started = started.replace(tzinfo=_tz.utc)
    return (now - started).total_seconds() < ttl_seconds


# ── 取代 mock：非串流版本（schema 向下相容）───────────────────

@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat_with_project(
    project_id: str,
    request: ChatRequest,
    user: AuthUser | None = Depends(get_optional_user),
):
    """與大專生計畫 PDF 對話（multi-agent 版本）"""
    document_ids = _get_document_ids_for_project(project_id) or None
    thread_id = request.thread_id or new_id()
    set_user_id(user.user_id if user else "")

    full_response = ""
    async for token, is_done, _ in route_agent_stream(
        request.message,
        thread_id=thread_id,
        document_ids=document_ids,
    ):
        if not is_done:
            full_response += token

    return ChatResponse(reply=full_response)


# ── 串流版本（前端主要使用）───────────────────────────────────

@router.post("/{project_id}/chat/stream")
async def chat_with_project_stream(
    project_id: str,
    request: ChatRequest,
    user: AuthUser | None = Depends(get_optional_user),
):
    """與大專生計畫 PDF 對話（SSE 串流版本）"""
    document_ids = _get_document_ids_for_project(project_id) or None
    thread_id = request.thread_id or new_id()
    user_id = user.user_id if user else None
    set_user_id(user_id or "")

    conv = _get_or_create_pdf_conversation(thread_id, user_id)

    # Mid-run steering：串流進行中收到同一 thread 的新訊息
    if conv.stream_started_at and _is_within_ttl(conv.stream_started_at):
        steering.set(thread_id, request.message)
        async def _ack():
            yield f"data: {_json.dumps({'token': '已收到補充，將納入考量。', 'done': True})}\n\n"
        return StreamingResponse(_ack(), media_type="text/event-stream")

    from datetime import datetime, timezone
    conv.stream_started_at = datetime.now(timezone.utc)
    with PdfSessionLocal() as db:
        db.merge(conv)
        db.commit()
    chat_jobs.start(thread_id, request.message, user_id=user_id, title=conv.title)

    async def event_stream():
        gate = get_gate()
        await gate.acquire()
        sources: list[str] = []
        try:
            async for token, is_done, src in route_agent_stream(
                request.message,
                thread_id=thread_id,
                document_ids=document_ids,
            ):
                if is_done:
                    sources = src
                else:
                    yield f"data: {_json.dumps({'token': token})}\n\n"
            yield f"data: {_json.dumps({'done': True, 'sources': sources, 'session_id': thread_id})}\n\n"
        finally:
            gate.release()
            chat_jobs.finish(thread_id)
            conv.stream_started_at = None
            with PdfSessionLocal() as db:
                db.merge(conv)
                db.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 取消串流 ────────────────────────────────────────────────

@router.post("/{project_id}/chat/{thread_id}/cancel")
async def cancel_project_chat(project_id: str, thread_id: str):
    chat_jobs.request_cancel(thread_id)
    return {"ok": True}
