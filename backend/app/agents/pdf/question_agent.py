from app.utils import new_id
import logging
import re
from collections.abc import AsyncIterator, Callable

from app.prompting.loader import load_stack

from .no_tool_runner import run_no_tool_agent, stream_no_tool_agent, write_agent_span
from .request_context import get_user_id
from .types import AgentLimitation, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

STACK_NAME = "question_default"
PROMPT_NAME = "question_skill"
AGENT_NAME = "question"


def trace_metadata(thread_id: str | None = None, document_ids: list[int] | None = None) -> dict[str, str | int]:
    stack = load_stack(STACK_NAME, _prompt_key(thread_id, document_ids))
    return {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }


def _prompt_key(thread_id: str | None, document_ids: list[int] | None) -> str:
    doc_key = ",".join(str(doc_id) for doc_id in sorted(document_ids or []))
    return f"{thread_id or ''}:{doc_key}"


def _has_questions(response: str) -> bool:
    markers = ("?", "\nQ", "\n-")
    return sum(response.count(marker) for marker in markers) >= 2


def _questions_have_varied_openings(response: str) -> bool:
    sentences = re.split(r"[?\n]", response)
    openings = [s.strip()[:4] for s in sentences if s.strip() and len(s.strip()) >= 4]
    if len(openings) < 2:
        return True
    return len(set(openings)) >= len(openings) - 1


async def answer(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
    evidence_context: str | None = None,
    evidence_sources: list[str] | None = None,
) -> AgentResult:
    extra_system_messages = [
        "You do not have retrieval tools in this step. Generate tutoring or "
        "student-facing questions only from the user request and any evidence "
        "context supplied by the router. Do not claim that you searched the "
        "documents yourself.",
    ]

    # Inject context_summary so follow-up questions are aware of prior research
    try:
        from app.services.pdf_agent_memory import build_memory_context, format_memory_system_messages
        memory = await build_memory_context(
            AGENT_NAME, thread_id, get_user_id(), user_message, document_ids
        )
        mem_msgs = format_memory_system_messages(memory)
        if mem_msgs:
            extra_system_messages = mem_msgs + extra_system_messages
    except Exception as _exc:
        logger.debug("question_agent.answer: memory context failed (non-fatal): %s", _exc)

    payload = {}
    if evidence_context:
        payload["evidence_context"] = evidence_context

    observation_id = observation_id or new_id()

    response, sources, meta, observation_id = await run_no_tool_agent(
        user_message=user_message,
        thread_id=thread_id,
        document_ids=document_ids,
        stack_name=STACK_NAME,
        prompt_name=PROMPT_NAME,
        agent_name=AGENT_NAME,
        observation_id=observation_id,
        trace_id=trace_id,
        use_mini=use_mini,
        extra_system_messages=extra_system_messages,
        payload=payload,
        sources=evidence_sources or [],
    )

    if not _has_questions(response) or not _questions_have_varied_openings(response):
        r2, s2, _, _ = await run_no_tool_agent(
            user_message=user_message,
            thread_id=thread_id,
            document_ids=document_ids,
            stack_name=STACK_NAME,
            prompt_name=PROMPT_NAME,
            agent_name=AGENT_NAME,
            observation_id=new_id(),
            trace_id=trace_id,
            use_mini=use_mini,
            extra_system_messages=[
                *extra_system_messages,
                "Retry because the previous output did not contain enough varied questions.",
            ],
            payload=payload,
            sources=evidence_sources or [],
        )
        if _has_questions(r2):
            response, sources = r2, s2

    _ev = evidence_sources or []
    return AgentResult(
        response=response,
        sources=sources,
        agent_name=AGENT_NAME,
        prompt_name=str(meta.get("prompt_name", PROMPT_NAME)),
        prompt_version=str(meta.get("prompt_version", "unknown")),
        observation_id=observation_id,
        status=AgentStatus(
            completed=True,
            work_summary=f"根據 {len(_ev)} 個來源生成題目。",
        ) if len(_ev) > 0 else AgentStatus(
            completed=False,
            work_summary="生成題目但缺乏充分文件依據。",
            gaps=["缺少足夠的文件內容作為題目依據"],
            agent_limitation=AgentLimitation.CONTEXT_INSUFFICIENT,
        ),
    )


async def _emit_stage(on_stage, msg: str) -> None:
    if not on_stage:
        return
    result = on_stage(msg)
    if hasattr(result, "__await__"):
        await result


async def stream(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    use_mini: bool = False,
    evidence_context: str | None = None,
    evidence_sources: list[str] | None = None,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    await _emit_stage(on_stage, "生成導讀問題中")
    observation_id = observation_id or new_id()
    extra_system_messages = [
        "You do not have retrieval tools in this step. Generate tutoring or "
        "student-facing questions only from the user request and any evidence "
        "context supplied by the router. Do not claim that you searched the "
        "documents yourself.",
    ]

    try:
        from app.services.pdf_agent_memory import build_memory_context, format_memory_system_messages
        memory = await build_memory_context(
            AGENT_NAME, thread_id, get_user_id(), user_message, document_ids
        )
        mem_msgs = format_memory_system_messages(memory)
        if mem_msgs:
            extra_system_messages = mem_msgs + extra_system_messages
    except Exception as _exc:
        logger.debug("question_agent.stream: memory context failed (non-fatal): %s", _exc)

    payload = {}
    if evidence_context:
        payload["evidence_context"] = evidence_context

    async for token in stream_no_tool_agent(
        user_message=user_message,
        thread_id=thread_id,
        document_ids=document_ids,
        stack_name=STACK_NAME,
        prompt_name=PROMPT_NAME,
        agent_name=AGENT_NAME,
        observation_id=observation_id,
        trace_id=trace_id,
        use_mini=use_mini,
        extra_system_messages=extra_system_messages,
        payload=payload,
        sources=evidence_sources or [],
    ):
        yield token, False, []
    yield "", True, evidence_sources or []
