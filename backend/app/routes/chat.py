"""
chat.py

POST /api/chat — ReAct Tool-Use 問答入口。

流程：
  1. 組裝學生背景 context_hint（系所、學院、年級偏好）
  2. LLM 自行決定呼叫哪些工具、呼叫幾次（最多 4 輪）
  3. 工具並行執行後結果回傳 LLM 生成最終回答
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services import llm_service as llm
from app.services import session_store as ss

router = APIRouter()


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None       # 不傳則自動建立新 session
    college: Optional[str] = None          # 限縮學院（加入 context hint）
    dept: Optional[str] = None             # 限縮系所（加入 context hint）
    include_grad: bool = False             # 是否包含研究所課程


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    tools_used: list[str]
    sources: list[dict]
    course_cards: list[dict] = []
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

    # 取得或建立 session
    sid = req.session_id or ss.new_session_id()
    history = ss.load(sid)

    # 組裝學生背景提示
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

    # 持久化這輪對話
    ss.save(sid, q, result["answer"])

    return ChatResponse(
        answer=result["answer"],
        session_id=sid,
        tools_used=result["tools_used"],
        sources=result["sources"],
        course_cards=result.get("course_cards", []),
        course_pool_count=result.get("course_pool_count", 0),
        has_large_result=result.get("has_large_result", False),
        model=result["model"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
    )


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
