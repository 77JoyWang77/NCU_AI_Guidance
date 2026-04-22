"""
chat.py

POST /api/chat          — ReAct Tool-Use 問答入口
POST /api/chat/stream   — SSE 串流版
GET  /api/chat/sessions — 列出所有對話
GET  /api/chat/session/{id} — 取得單一對話完整資料
"""

import json as _json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.services import llm_service as llm
from app.services import session_store as ss

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    college: Optional[str] = None
    dept: Optional[str] = None
    include_grad: bool = False


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    tools_used: list[str]
    sources: list[dict]
    course_cards: list[dict] = []
    course_pool: list[dict] = []
    course_pool_count: int = 0
    has_large_result: bool = False
    model: str
    input_tokens: int
    output_tokens: int


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question 不得為空")

    sid = req.session_id or ss.new_session_id()
    history = ss.load(sid)

    hints = []
    if req.dept:
        hints.append(f"學生系所：{req.dept}")
    if req.college:
        hints.append(f"學院：{req.college}")
    if req.include_grad:
        hints.append("需包含研究所課程")
    context_hint = "、".join(hints) if hints else ""

    result = llm.generate_with_tools(
        question=q,
        history=history,
        context_hint=context_hint,
    )

    ss.save(
        sid, q, result["answer"],
        course_cards=result.get("course_cards", []),
        tools_used=result.get("tools_used", []),
    )

    return ChatResponse(
        answer=result["answer"],
        session_id=sid,
        tools_used=result["tools_used"],
        sources=result["sources"],
        course_cards=result.get("course_cards", []),
        course_pool=result.get("course_pool", []),
        course_pool_count=result.get("course_pool_count", 0),
        has_large_result=result.get("has_large_result", False),
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """串流版：SSE 逐字回傳 + 工具呼叫進度事件。"""
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question 不得為空")

    sid = req.session_id or ss.new_session_id()
    history = ss.load(sid)

    hints = []
    if req.dept:
        hints.append(f"學生系所：{req.dept}")
    if req.college:
        hints.append(f"學院：{req.college}")
    if req.include_grad:
        hints.append("需包含研究所課程")
    context_hint = "、".join(hints) if hints else ""

    answer_buf: list[str] = []

    def _generate():
        for raw in llm.stream_with_tools(
            question=q,
            history=history,
            context_hint=context_hint,
        ):
            if raw.startswith("data: "):
                try:
                    data = _json.loads(raw[6:])
                    if data.get("type") == "token":
                        answer_buf.append(data.get("text", ""))
                    elif data.get("type") == "done":
                        data["session_id"] = sid
                        ss.save(
                            sid, q, "".join(answer_buf),
                            course_cards=data.get("course_cards", []),
                            tools_used=data.get("tools_used", []),
                            course_pool=data.get("course_pool", []),
                            debug_trace=data.get("debug_trace"),
                        )
                        raw = f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
            yield raw

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class CourseDetailRequest(BaseModel):
    name: str
    code: str = ""


@router.post("/course_detail")
async def get_course_detail(req: CourseDetailRequest):
    """以課名查詢完整課程資訊（含課程目標、內容、評分等）。"""
    from app.services import retriever

    if req.name:
        results = retriever.get_courses_by_name(req.name)
        if results:
            r = results[0]
            meta = r.get("metadata", {})
            return {
                "name":             meta.get("name_zh", req.name),
                "dept":             meta.get("dept", ""),
                "credits":          meta.get("credits", 0),
                "type":             meta.get("type", ""),
                "teacher":          meta.get("teacher", ""),
                "code":             meta.get("course_code", req.code),
                "summary":          r.get("document", "")[:300],
                "course_objective": meta.get("course_objective", ""),
                "course_content":   meta.get("course_content", ""),
                "grading":          meta.get("grading", ""),
                "when_raw":         meta.get("when_raw", ""),
                "prereq_codes":     meta.get("prereq_codes", ""),
                "eligible_years":   meta.get("eligible_years", ""),
            }

    results = retriever.search_courses(req.name or req.code, n_results=1)
    if results:
        r = results[0]
        meta = r.get("metadata", {})
        return {
            "name":             meta.get("name_zh", req.name),
            "dept":             meta.get("dept", ""),
            "credits":          meta.get("credits", 0),
            "type":             meta.get("type", ""),
            "teacher":          meta.get("teacher", ""),
            "code":             meta.get("course_code", req.code),
            "summary":          r.get("document", "")[:300],
            "course_objective": meta.get("course_objective", ""),
            "course_content":   meta.get("course_content", ""),
            "grading":          meta.get("grading", ""),
            "when_raw":         meta.get("when_raw", ""),
            "prereq_codes":     meta.get("prereq_codes", ""),
            "eligible_years":   meta.get("eligible_years", ""),
        }
    return {}


@router.get("/sessions")
async def list_sessions():
    """列出所有對話摘要（session_id、標題、更新時間、輪數）。"""
    return ss.list_sessions()


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """取得單一對話完整資料（含每輪課程卡片與工具紀錄）。"""
    data = ss.get_display(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """清除對話記錄（前端「開新對話」按鈕用）"""
    deleted = ss.delete(session_id)
    return {"deleted": deleted, "session_id": session_id}


@router.get("/tools")
async def list_tools():
    """列出可用工具及說明（除錯用）"""
    from app.services.tools import TOOLS
    return {
        "tools": [
            {
                "name": t["function"]["name"],
                "desc": t["function"]["description"],
            }
            for t in TOOLS
        ]
    }
