"""Output evaluation agent (no Langfuse, no TraceV2)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from app.pdf_config import pdf_settings
from app.prompting.loader import load_stack

logger = logging.getLogger(__name__)

PROMPT_NAME = "evaluation_agent"
AGENT_NAME = "evaluation"
STACK_NAME = "evaluation_default"


class EvaluationResult(BaseModel):
    grounding: float = Field(ge=0, le=5)
    task_fit: float = Field(ge=0, le=5)
    completeness: float = Field(ge=0, le=5)
    specificity: float = Field(ge=0, le=5)
    source_quality: float = Field(ge=0, le=5)
    uncertainty_honesty: float = Field(ge=0, le=5)
    format_fit: float = Field(ge=0, le=5)
    overall: float = Field(default=0.0, ge=0, le=5)
    dimension_reasoning: dict[str, str] = Field(default_factory=dict)
    verdict: str = Field(description="Short verdict in Traditional Chinese.")
    failure_modes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)


WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "chat": {
        "grounding": 0.15, "task_fit": 0.25, "completeness": 0.15,
        "specificity": 0.12, "source_quality": 0.08, "uncertainty_honesty": 0.15, "format_fit": 0.10,
    },
    "retrieval": {
        "grounding": 0.30, "task_fit": 0.20, "completeness": 0.15,
        "specificity": 0.12, "source_quality": 0.10, "uncertainty_honesty": 0.08, "format_fit": 0.05,
    },
    "research": {
        "grounding": 0.25, "task_fit": 0.18, "completeness": 0.22,
        "specificity": 0.12, "source_quality": 0.10, "uncertainty_honesty": 0.08, "format_fit": 0.05,
    },
    "question": {
        "grounding": 0.10, "task_fit": 0.25, "completeness": 0.20,
        "specificity": 0.15, "source_quality": 0.08, "uncertainty_honesty": 0.07, "format_fit": 0.15,
    },
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "grounding": 0.25, "task_fit": 0.18, "completeness": 0.17,
    "specificity": 0.12, "source_quality": 0.10, "uncertainty_honesty": 0.10, "format_fit": 0.08,
}


def _llm():
    return AzureChatOpenAI(
        azure_deployment=pdf_settings.azure_mini_deployment or pdf_settings.azure_chat_deployment,
        azure_endpoint=pdf_settings.azure_openai_endpoint,
        api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
        api_version=pdf_settings.azure_openai_api_version,
        temperature=0,
    )


def _weighted_overall(result: EvaluationResult, agent_name: str = "chat") -> float:
    weights = WEIGHT_PROFILES.get(agent_name, DEFAULT_WEIGHTS)
    raw = sum(getattr(result, dim) * w for dim, w in weights.items())
    return max(0.0, min(5.0, round(raw, 2)))


def _json_loads(value: str | dict | list | None) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


async def evaluate_output(
    *,
    user_task: str,
    answer: str,
    agent_name: str = "chat",
    sources: list[str] | None = None,
    trace_summary: dict | None = None,
    extra_context: dict | None = None,
) -> EvaluationResult:
    """Evaluate an answer without mutating application state."""
    trace_summary = trace_summary or {}
    sources = sources or []
    answer_limit = 8000 if agent_name == "research" else 5000
    payload = {
        "user_task": user_task,
        "answer": answer[:answer_limit],
        "agent_name": agent_name,
        "sources": sources[:12],
        "sources_empty": not sources,
        "trace_summary": trace_summary,
        "extra_context": extra_context or {},
        "response_contract": {
            "failure_modes_max": 5,
            "suggested_fixes_max": 3,
        },
    }
    stack = load_stack(STACK_NAME)
    system_messages = [SystemMessage(content=content) for content in stack.contents]
    scorer = _llm().with_structured_output(EvaluationResult)
    result: EvaluationResult = await scorer.ainvoke([
        *system_messages,
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ])
    if not sources:
        result = result.model_copy(update={"source_quality": 0.0})
    return result.model_copy(update={"overall": _weighted_overall(result, agent_name)})


async def evaluate_direct_answer(
    *,
    user_task: str,
    answer: str,
    sources: list[str],
    agent_name: str = "chat",
) -> EvaluationResult | None:
    try:
        return await evaluate_output(
            user_task=user_task,
            answer=answer,
            agent_name=agent_name,
            sources=sources,
        )
    except Exception as exc:
        logger.warning("evaluate_direct_answer failed: %s", exc)
        return None


async def evaluate_latest_thread_message(
    thread_id: str,
    *,
    exclude_observation_id: str | None = None,
) -> EvaluationResult | None:
    def _find():
        from app.database_pdf import PdfSessionLocal
        from app.models.pdf_models import PdfAgentMessage
        with PdfSessionLocal() as db:
            q = db.query(PdfAgentMessage).filter(
                PdfAgentMessage.thread_id == thread_id,
                PdfAgentMessage.agent_answer.isnot(None),
            )
            if exclude_observation_id:
                q = q.filter(PdfAgentMessage.observation_id != exclude_observation_id)
            return q.order_by(PdfAgentMessage.created_at.desc()).first()

    msg = await asyncio.to_thread(_find)
    if not msg:
        return None
    return await evaluate_output(
        user_task=msg.user_question or "",
        answer=msg.agent_answer or "",
        sources=msg.sources or [],
        trace_summary=msg.trace_summary or {},
        agent_name=msg.agent_name,
    )


def format_evaluation_for_user(result: EvaluationResult | None) -> str:
    if result is None:
        return "找不到可評估的最近一次輸出。"
    lines = [
        f"評估結果：{result.verdict}",
        f"總分：{result.overall:.1f}/5",
        f"證據支撐：{result.grounding:.1f}，任務符合：{result.task_fit:.1f}，完整度：{result.completeness:.1f}",
    ]
    if result.failure_modes:
        lines.append("問題類型：" + "、".join(result.failure_modes[:3]))
    if result.suggested_fixes:
        lines.append("建議修正：" + "；".join(result.suggested_fixes[:3]))
    return "\n".join(lines)
