"""
chat.py

POST /api/chat          — ReAct Tool-Use 問答入口
POST /api/chat/stream   — SSE 串流版
GET  /api/chat/sessions — 列出所有對話
GET  /api/chat/session/{id} — 取得單一對話完整資料
"""

import json as _json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.services import llm_service as llm
from app.services import session_store as ss
from app.services.auth_service import AuthUser, get_optional_user

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
async def chat(req: ChatRequest, user: AuthUser | None = Depends(get_optional_user)):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question 不得為空")

    sid = req.session_id or ss.new_session_id()
    user_id = user.user_id if user else None
    history = ss.load(sid, user_id=user_id)

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
        user_id=user_id,
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
async def chat_stream(req: ChatRequest, user: AuthUser | None = Depends(get_optional_user)):
    """串流版：SSE 逐字回傳 + 工具呼叫進度事件。"""
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question 不得為空")

    sid = req.session_id or ss.new_session_id()
    user_id = user.user_id if user else None
    history = ss.load(sid, user_id=user_id)

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
                            user_id=user_id,
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


# ── course_index 載入（啟動時讀一次，之後 in-memory）────────────────────────
from functools import lru_cache
from pathlib import Path as _Path

@lru_cache(maxsize=1)
def _load_course_index() -> dict:
    path = _Path(__file__).parent.parent.parent.parent / "data" / "processed" / "course_index.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return _json.load(f)


def _lookup_course(name: str, code: str) -> dict | None:
    """以 code 精確查，找不到再用 name 全表掃描。"""
    idx = _load_course_index()
    if not idx:
        return None
    # 1. code 精確查
    if code and code in idx:
        return idx[code]
    # 2. name 全表掃描（取第一個 name_zh 吻合的）
    if name:
        name_lower = name.strip().lower()
        for entry in idx.values():
            if entry.get("name_zh", "").strip().lower() == name_lower:
                return entry
    return None


@router.post("/course_detail")
async def get_course_detail(req: CourseDetailRequest):
    """以課名或課號查詢完整課程資訊（從 course_index.json，不走 Qdrant）。"""
    entry = _lookup_course(req.name, req.code)
    if not entry:
        return {}

    sections = entry.get("sections", [])
    has_multi = len(sections) > 0

    return {
        "name":    entry.get("name_zh", req.name),
        "name_en": entry.get("name_en", ""),
        "dept":    entry.get("dept", ""),
        "college": entry.get("college", ""),
        "credits": entry.get("credits", 0),
        "type":    entry.get("type", ""),
        "teacher": entry.get("teacher", ""),
        "code":    req.code or "",
        "is_grad": entry.get("is_grad", False),
        # 課綱
        "course_objective": entry.get("objective", ""),
        "course_content":   entry.get("content", ""),
        "textbook":         entry.get("textbook", ""),
        # 修習資訊
        "when_schedule": entry.get("when_schedule", []),
        "prereq_codes":  ", ".join(entry.get("prereq_codes", [])),
        "coreq_codes":   ", ".join(entry.get("coreq_codes", [])),
        # 分發條件：單班直接給字串，多班給 sections 陣列
        "eligibility_text": entry.get("eligibility_text", "") if not has_multi else "",
        "sections":         sections if has_multi else [],
        # NLP
        "concepts":            entry.get("concepts", []),
        "languages":           entry.get("languages", []),
        "tools":               entry.get("tools", []),
        "topic_tags":          entry.get("topic_tags", []),
        "core_questions":      entry.get("core_questions", []),
        "simplified_concepts": entry.get("simplified_concepts", []),
        "domain_tags":         entry.get("domain_tags", []),
    }


@router.get("/sessions")
async def list_sessions(user: AuthUser | None = Depends(get_optional_user)):
    """列出所有對話摘要（session_id、標題、更新時間、輪數）。"""
    return ss.list_sessions(user_id=user.user_id if user else None)


@router.get("/session/{session_id}")
async def get_session(session_id: str, user: AuthUser | None = Depends(get_optional_user)):
    """取得單一對話完整資料（含每輪課程卡片與工具紀錄）。"""
    data = ss.get_display(session_id, user_id=user.user_id if user else None)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@router.delete("/session/{session_id}")
async def delete_session(session_id: str, user: AuthUser | None = Depends(get_optional_user)):
    """清除對話記錄（前端「開新對話」按鈕用）"""
    deleted = ss.delete(session_id, user_id=user.user_id if user else None)
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
