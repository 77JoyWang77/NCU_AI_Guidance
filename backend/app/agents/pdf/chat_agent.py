from app.utils import new_id
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import asyncio
import json
import logging
from typing import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.pdf_config import pdf_settings
from .no_tool_runner import run_no_tool_agent, stream_no_tool_agent, write_agent_span
from .request_context import get_user_id  # noqa: F401
from app.prompting.loader import load_stack

from .types import AgentResult, AgentStatus

STACK_NAME = "chat_default"
PROMPT_NAME = "chat_mode"
AGENT_NAME = "chat"

logger = logging.getLogger(__name__)


async def _emit_stage(on_stage, msg: str) -> None:
    if not on_stage:
        return
    try:
        result = on_stage(msg)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass


def trace_metadata() -> dict[str, str | int]:
    stack = load_stack(STACK_NAME)
    return {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }


def _llm(use_mini: bool = False) -> AzureChatOpenAI:
    deployment = (
        pdf_settings.azure_mini_deployment
        if use_mini and pdf_settings.azure_mini_deployment
        else pdf_settings.azure_chat_deployment
    )
    return AzureChatOpenAI(
        azure_deployment=deployment,
        azure_endpoint=pdf_settings.azure_openai_endpoint,
        api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
        api_version=pdf_settings.azure_openai_api_version,
        temperature=0.2,
    )


async def compose_final_response(
    *,
    user_message: str,
    task_result: AgentResult,
    thread_id: str,
    document_ids: list[int] | None = None,
    observation_id: str | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
) -> AgentResult:
    """Format a task-agent result for the user without routing or tool access."""
    observation_id = observation_id or new_id()
    stack = load_stack(STACK_NAME)
    metadata = {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }
    system_messages = [SystemMessage(content=content) for content in stack.contents]
    system_messages.append(SystemMessage(content=(
        "You are formatting the final user-facing response from an existing "
        "task-agent result. Do not perform routing. Do not add facts, evidence, "
        "or content that does not appear in the task-agent answer. "
        "If the task-agent answer says content was not found or is incomplete, "
        "preserve that incompleteness — do not fill gaps with your own knowledge. "
        "Preserve all technical terms, classification names, and taxonomy labels "
        "verbatim; never substitute them with synonyms or paraphrases."
    )))
    payload = {
        "user_message": user_message,
        "task_agent": task_result.agent_name,
        "task_answer": task_result.response,
        "sources": task_result.sources,
        "response_contract": {
            "language": "Match the user's language.",
            "preserve_sources": True,
            "do_not_add_new_facts": True,
        },
    }
    messages = [
        *system_messages,
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
    response = await _llm(use_mini=use_mini).ainvoke(messages)
    content = str(getattr(response, "content", response)).strip()
    return AgentResult(
        response=content,
        sources=task_result.sources,
        agent_name=AGENT_NAME,
        prompt_name=str(metadata.get("prompt_name", PROMPT_NAME)),
        prompt_version=str(metadata.get("prompt_version", "unknown")),
        observation_id=observation_id,
        status=AgentStatus(
            completed=True,
            work_summary="從對話 context 和文件摘要回答。" if document_ids else "從對話 context 回答（無文件）。",
        ),
    )


async def answer(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    use_mini: bool = False,
) -> AgentResult:
    stack = load_stack(STACK_NAME)
    meta = {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }
    await _emit_stage(on_stage, "組織回答中")
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
        extra_system_messages=[
            "You do not have retrieval tools in this step. If the request "
            "requires document evidence, answer only from context already "
            "provided by the router or state that the router should use a "
            "retrieval/research route."
        ],
    )
    _insufficient = "[INSUFFICIENT_CONTEXT]" in response
    response = response.replace("[INSUFFICIENT_CONTEXT]", "").strip()

    return AgentResult(
        response=response,
        sources=sources,
        agent_name=AGENT_NAME,
        prompt_name=str(meta.get("prompt_name", PROMPT_NAME)),
        prompt_version=str(meta.get("prompt_version", "unknown")),
        observation_id=observation_id,
        status=AgentStatus(
            completed=not _insufficient,
            work_summary="直接從對話 context 回答。",
            agent_limitation="chat 無文件搜尋工具，現有 context 不足以充分回答" if _insufficient else "",
        ),
    )


async def stream(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    use_mini: bool = False,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    observation_id = observation_id or new_id()
    await _emit_stage(on_stage, "組織回答中")
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
        extra_system_messages=[
            "You do not have retrieval tools in this step. If the request "
            "requires document evidence, answer only from context already "
            "provided by the router or state that the router should use a "
            "retrieval/research route."
        ],
    ):
        yield token, False, []
    yield "", True, []
