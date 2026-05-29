"""No-tool LLM execution for agents that must not call retrieval tools."""
from __future__ import annotations

from app.utils import new_id

import json
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.pdf_config import pdf_settings
from app.prompting.loader import load_stack

from .request_context import get_user_id  # noqa: F401 — kept for callers that import get_user_id here

logger = logging.getLogger(__name__)

_chat_llm: AzureChatOpenAI | None = None
_mini_llm_instance: AzureChatOpenAI | None = None


def _get_llm(use_mini: bool = False) -> AzureChatOpenAI:
    global _chat_llm, _mini_llm_instance
    if use_mini and pdf_settings.azure_mini_deployment:
        if _mini_llm_instance is None:
            _mini_llm_instance = AzureChatOpenAI(
                azure_deployment=pdf_settings.azure_mini_deployment,
                azure_endpoint=pdf_settings.azure_openai_endpoint,
                api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
                api_version=pdf_settings.azure_openai_api_version,
                temperature=0.2,
            )
        return _mini_llm_instance
    if _chat_llm is None:
        _chat_llm = AzureChatOpenAI(
            azure_deployment=pdf_settings.azure_chat_deployment,
            azure_endpoint=pdf_settings.azure_openai_endpoint,
            api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
            api_version=pdf_settings.azure_openai_api_version,
            temperature=0.2,
        )
    return _chat_llm


def _get_document_abstracts(document_ids: list[int]) -> list[dict]:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument
    with PdfSessionLocal() as db:
        rows = (
            db.query(PdfDocument.id, PdfDocument.filename, PdfDocument.abstract_text)
            .filter(PdfDocument.status == "ready", PdfDocument.id.in_(document_ids))
            .all()
        )
    return [{"filename": r.filename, "abstract": r.abstract_text} for r in rows if r.abstract_text]


def _prepare_no_tool_call(
    *,
    user_message: str,
    stack_name: str,
    agent_name: str,
    document_ids: list[int] | None = None,
    extra_system_messages: list[str] | None = None,
) -> tuple[list, dict]:
    stack = load_stack(stack_name)
    metadata = {
        "agent_name": agent_name,
        **stack.metadata(),
    }

    messages = [SystemMessage(content=content) for content in stack.contents]
    if document_ids:
        abstracts = _get_document_abstracts(document_ids)
        if abstracts:
            messages.append(SystemMessage(content=(
                "以下是本次對話引用的論文摘要，請以此作為背景資訊：\n\n" + abstracts[0]["abstract"]
            )))
    for content in extra_system_messages or []:
        if content:
            messages.append(SystemMessage(content=content))
    messages.append(HumanMessage(content=json.dumps({"user_message": user_message}, ensure_ascii=False)))
    return messages, metadata


async def run_no_tool_agent(
    *,
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None,
    stack_name: str,
    agent_name: str,
    observation_id: str | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
    extra_system_messages: list[str] | None = None,
) -> tuple[str, list[str], dict, str]:
    """Run one no-tool LLM call."""
    observation_id = observation_id or new_id()
    messages, metadata = _prepare_no_tool_call(
        user_message=user_message,
        stack_name=stack_name,
        agent_name=agent_name,
        document_ids=document_ids,
        extra_system_messages=extra_system_messages,
    )

    _llm_instance = _get_llm(use_mini=use_mini)
    response = await _llm_instance.ainvoke(messages)
    content = str(getattr(response, "content", response)).strip()
    return content, [], metadata, observation_id


async def stream_no_tool_agent(
    *,
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None,
    stack_name: str,
    agent_name: str,
    observation_id: str | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
    extra_system_messages: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream one no-tool LLM call token-by-token."""
    observation_id = observation_id or new_id()
    messages, metadata = _prepare_no_tool_call(
        user_message=user_message,
        stack_name=stack_name,
        agent_name=agent_name,
        document_ids=document_ids,
        extra_system_messages=extra_system_messages,
    )

    llm_instance = _get_llm(use_mini=use_mini)
    async for chunk in llm_instance.astream(messages):
        yield chunk.content or ""
