import asyncio
import json as _json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.models.schemas import Project, ChatRequest, ChatResponse
from app.services.auth_service import get_optional_user, AuthUser

logger = logging.getLogger(__name__)
router = APIRouter()

# Per-user stream lock: prevents duplicate concurrent requests for the same user+project.
# Key: "{project_id}:{user_id_or_anon}"
_stream_lock: dict[str, str] = {}  # key → active thread_id
_stream_lock_mutex = asyncio.Lock()  # makes check-and-set atomic within a single asyncio worker

HEARTBEAT_INTERVAL = 15.0  # seconds between SSE heartbeats while waiting for LLM tokens


# ── 資料載入 ───────────────────────────────────────────────────────────────────

def load_projects():
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'processed', 'projects.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        projects = _json.load(f)
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


# ── 既有 GET endpoints（不動）──────────────────────────────────────────────────

@router.get("", response_model=List[Project])
async def get_projects(
    department: Optional[str] = Query(None, description="科系篩選"),
    year: Optional[str] = Query(None, description="學年度篩選"),
):
    projects = load_projects()
    if department:
        projects = [p for p in projects if p['department'] == department]
    if year:
        projects = [p for p in projects if p['year'] == year]
    return projects


@router.get("/{project_id}", response_model=Project)
async def get_project_by_id(project_id: str):
    for project in load_projects():
        if project['id'] == project_id:
            return project
    return {"error": "Project not found"}


# ── PDF chat 輔助函式 ──────────────────────────────────────────────────────────

def _get_document_ids_for_project(project_id: str) -> list[int]:
    """project_id → pdf_documents.id，比對 pdfPath 檔名。"""
    try:
        from app.database_pdf import PdfSessionLocal
        from app.models.pdf_models import PdfDocument

        project = next((p for p in load_projects() if p["id"] == project_id), None)
        if not project or not project.get("pdfPath"):
            return []
        filename = project["pdfPath"].replace("\\", "/").split("/")[-1]
        with PdfSessionLocal() as db:
            doc = db.query(PdfDocument.id).filter(
                PdfDocument.filename.ilike(f"%{filename}%"),
                PdfDocument.status == "ready",
            ).first()
        return [doc.id] if doc else []
    except Exception as exc:
        logger.warning("_get_document_ids_for_project failed: %s", exc)
        return []


def _get_or_create_pdf_conversation(thread_id: str, user_id: str | None):
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfConversation

    with PdfSessionLocal() as db:
        conv = db.query(PdfConversation).filter_by(thread_id=thread_id).first()
        if not conv:
            conv = PdfConversation(thread_id=thread_id, user_id=user_id)
            db.add(conv)
            db.commit()
            db.refresh(conv)
    return conv


def _is_within_ttl(stream_started_at: datetime, ttl_seconds: int = 30) -> bool:
    return (datetime.now(timezone.utc) - stream_started_at).total_seconds() < ttl_seconds


def _mark_stream(thread_id: str, started_at: datetime | None) -> None:
    try:
        from app.database_pdf import PdfSessionLocal
        from app.models.pdf_models import PdfConversation

        with PdfSessionLocal() as db:
            conv = db.query(PdfConversation).filter_by(thread_id=thread_id).first()
            if conv:
                conv.stream_started_at = started_at
                db.commit()
    except Exception as exc:
        logger.debug("_mark_stream failed: %s", exc)


# ── 非串流 chat（向下相容原有 schema）────────────────────────────────────────────

@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat_with_project(
    project_id: str,
    request: ChatRequest,
    user: Optional[AuthUser] = Depends(get_optional_user),
):
    from app.utils import new_id
    from app.agents.pdf.router_agent import route_agent_stream
    from app.agents.pdf.request_context import set_user_id

    document_ids = _get_document_ids_for_project(project_id) or None
    thread_id = request.thread_id or new_id()
    set_user_id(user.user_id if user else "")

    full_response = ""
    try:
        async for token, is_done, _ in route_agent_stream(
            request.message,
            thread_id=thread_id,
            document_ids=document_ids,
        ):
            if not is_done:
                full_response += token
    except Exception as exc:
        logger.error("chat_with_project error: %s", exc)
        full_response = "抱歉，處理您的問題時發生錯誤，請稍後再試。"

    return ChatResponse(reply=full_response)


# ── SSE 串流 chat（前端主要使用）──────────────────────────────────────────────────

@router.post("/{project_id}/chat/stream")
async def chat_with_project_stream(
    project_id: str,
    request: ChatRequest,
    user: Optional[AuthUser] = Depends(get_optional_user),
):
    from app.utils import new_id
    from app.agents.pdf import chat_jobs, steering
    from app.agents.pdf.router_agent import route_agent_stream
    from app.agents.pdf.request_context import set_user_id

    document_ids = _get_document_ids_for_project(project_id) or None
    thread_id = request.thread_id or new_id()
    user_id = user.user_id if user else None
    set_user_id(user_id or "")

    # Per-user stream lock: if same user+project already has an active stream,
    # silently drop the duplicate request so the frontend only sees one response.
    # Mutex makes the check-and-set atomic within a single asyncio worker.
    lock_key = f"{project_id}:{user_id or 'anon'}"
    async with _stream_lock_mutex:
        if lock_key in _stream_lock:
            _active = _stream_lock[lock_key]
            logger.warning("duplicate stream dropped project=%s user=%s active_thread=%s",
                           project_id, user_id, _active)

            async def _drop():
                yield f"data: {_json.dumps({'done': True, 'session_id': _active})}\n\n"

            return StreamingResponse(_drop(), media_type="text/event-stream")

        _stream_lock[lock_key] = thread_id

    logger.info("stream request project=%s thread=%s has_thread_in_req=%s",
                project_id, thread_id, bool(request.thread_id))

    conv = _get_or_create_pdf_conversation(thread_id, user_id)

    # Mid-run steering：同一 thread 在串流中補送訊息
    if conv.stream_started_at and _is_within_ttl(conv.stream_started_at):
        steering.set(thread_id, request.message)
        _stream_lock.pop(lock_key, None)

        async def _ack():
            yield f"data: {_json.dumps({'token': '已收到補充，將納入考量。', 'done': True})}\n\n"

        return StreamingResponse(_ack(), media_type="text/event-stream")

    _mark_stream(thread_id, datetime.now(timezone.utc))
    chat_jobs.start(thread_id, request.message, user_id=user_id, title=conv.title)

    async def event_stream():
        from app.services.pdf_llm_gate import acquire_with_timeout, get_gate

        gate_acquired = await acquire_with_timeout(timeout=30.0)
        if not gate_acquired:
            yield f"data: {_json.dumps({'error': '服務目前繁忙，請稍後再試。', 'done': True, 'session_id': thread_id})}\n\n"
            _stream_lock.pop(lock_key, None)
            return

        pending: asyncio.Task | None = None
        try:
            aiter = route_agent_stream(
                request.message,
                thread_id=thread_id,
                document_ids=document_ids,
            ).__aiter__()

            pending = asyncio.create_task(aiter.__anext__())
            while True:
                try:
                    result = await asyncio.wait_for(asyncio.shield(pending), timeout=HEARTBEAT_INTERVAL)
                except asyncio.TimeoutError:
                    yield f"data: {_json.dumps({'heartbeat': True})}\n\n"
                    continue
                except StopAsyncIteration:
                    break

                token, is_done, sources = result
                if is_done == "replace":
                    yield f"data: {_json.dumps({'replace': token, 'sources': sources})}\n\n"
                elif is_done:
                    yield f"data: {_json.dumps({'done': True, 'session_id': thread_id, 'cancelled': chat_jobs.is_cancelled(thread_id)})}\n\n"
                    break
                else:
                    yield f"data: {_json.dumps({'token': token})}\n\n"

                pending = asyncio.create_task(aiter.__anext__())

        except Exception as exc:
            logger.error("event_stream error thread=%s: %s", thread_id, exc)
            yield f"data: {_json.dumps({'token': '處理時發生錯誤，請稍後再試。', 'done': True, 'session_id': thread_id})}\n\n"
        finally:
            if pending and not pending.done():
                pending.cancel()
            get_gate().release()
            chat_jobs.finish(thread_id)
            _mark_stream(thread_id, None)
            _stream_lock.pop(lock_key, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 取消串流 ────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/chat/{thread_id}/cancel")
async def cancel_project_chat(project_id: str, thread_id: str):
    from app.agents.pdf import chat_jobs
    chat_jobs.request_cancel(thread_id)
    return {"ok": True}
