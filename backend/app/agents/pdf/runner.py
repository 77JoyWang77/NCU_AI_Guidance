import asyncio
import json
import logging
import re
import warnings
from collections.abc import AsyncIterator
from typing import Callable, Any
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ClearToolUsesEdit,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ModelResponse,
    SummarizationMiddleware,
    ToolRetryMiddleware,
    after_model,
    dynamic_prompt,
    wrap_model_call,
    ModelRequest,
)
from langchain.agents.structured_output import ProviderStrategy, StructuredOutputValidationError
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from .request_context import get_user_id

warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module="pydantic",
)

from app.pdf_config import pdf_settings
from app.tools.rag_tool import (
    AgentContext,
    TOOLS,
    set_query_expander_llm,
)

logger = logging.getLogger(__name__)


class _AnswerExtractor:
    """從 AgentResponse JSON stream 中即時提取 answer 欄位 token。"""

    def __init__(self) -> None:
        self._buf = ""
        self._in_answer = False
        self._escape = False
        self._done = False

    def process(self, token: str) -> str:
        if self._done:
            return ""
        if not self._in_answer:
            self._buf += token
            m = re.search(r'"answer"\s*:\s*"', self._buf)
            if m:
                self._in_answer = True
                remainder = self._buf[m.end():]
                self._buf = ""
                return self._consume(remainder)
            return ""
        return self._consume(token)

    def _consume(self, text: str) -> str:
        out: list[str] = []
        for ch in text:
            if self._escape:
                out.append(ch)
                self._escape = False
            elif ch == "\\":
                out.append(ch)
                self._escape = True
            elif ch == '"':
                self._done = True
                break
            else:
                out.append(ch)
        return "".join(out)

    @property
    def produced_output(self) -> bool:
        return self._done or self._in_answer


def _get_abstracts(document_ids: list[int] | None) -> list[dict]:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument
    with PdfSessionLocal() as db:
        q = db.query(PdfDocument.id, PdfDocument.filename, PdfDocument.abstract_text).filter(
            PdfDocument.status == "ready"
        )
        if document_ids:
            q = q.filter(PdfDocument.id.in_(document_ids))
        return [
            {"filename": row.filename, "abstract": row.abstract_text}
            for row in q.all()
            if row.abstract_text
        ]


_checkpointer: AsyncPostgresSaver | None = None
_store: AsyncPostgresStore | None = None
_pool = None
_tool_agent = None
_tool_agent_mini = None
_llm = None
_agent_llm = None
_mini_llm = None
_mini_agent_llm = None

SYSTEM_PROMPT = "You are an AI research assistant. Follow the request-specific system messages."


class AgentResponse(BaseModel):
    answer: str = Field(description="Complete answer to the user's question")
    sources: list[str] = Field(
        default_factory=list,
        description='Leave empty — sources are not displayed to the user.',
        max_length=3,
    )


def _get_llm():
    global _llm, _agent_llm
    if _llm is None:
        _llm = AzureChatOpenAI(
            azure_deployment=pdf_settings.azure_chat_deployment,
            azure_endpoint=pdf_settings.azure_openai_endpoint,
            api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
            api_version=pdf_settings.azure_openai_api_version,
            temperature=0.3,
        )
        _agent_llm = _llm.bind(parallel_tool_calls=False)
        set_query_expander_llm(_llm)
    return _llm


def _get_agent_llm():
    global _agent_llm
    if _agent_llm is None:
        _get_llm()
    return _agent_llm


def _get_mini_llm():
    global _mini_llm, _mini_agent_llm
    if _mini_llm is None:
        _mini_llm = AzureChatOpenAI(
            azure_deployment=pdf_settings.azure_mini_deployment,
            azure_endpoint=pdf_settings.azure_openai_endpoint,
            api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
            api_version=pdf_settings.azure_openai_api_version,
            temperature=0.3,
        )
        _mini_agent_llm = _mini_llm.bind(parallel_tool_calls=False)
    return _mini_llm


def _get_mini_agent_llm():
    global _mini_agent_llm
    if _mini_agent_llm is None:
        _get_mini_llm()
    return _mini_agent_llm


@after_model
def _track_model_cost(state: dict, runtime) -> None:
    try:
        messages = state.get("messages", [])
        response = messages[-1] if messages else None
        if response is None:
            return
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return
        ctx = getattr(runtime, "context", None)
        agent_name_ctx = getattr(ctx, "agent_name", None) or "unknown"
        thread_id = (getattr(ctx, "thread_id", None) or "")[:8]
        model_name = (getattr(response, "response_metadata", None) or {}).get("model_name", "")
        cache_read = (usage.get("input_token_details") or {}).get("cache_read", 0)
        logger.info(
            "model_cost agent=%s thread=%s in=%d out=%d total=%d cache_read=%d model=%s",
            agent_name_ctx, thread_id,
            usage.get("input_tokens", 0), usage.get("output_tokens", 0),
            usage.get("total_tokens", 0), cache_read, model_name,
        )
    except Exception:
        pass


@wrap_model_call
async def _trim_messages(request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
    messages = request.messages
    if len(messages) <= 20:
        return await handler(request)
    tail = messages[-20:]
    for i, msg in enumerate(tail):
        if isinstance(msg, HumanMessage):
            tail = tail[i:]
            break
    else:
        tail = tail[-10:]
    return await handler(request.override(messages=tail))


@dynamic_prompt
async def _memory_prompt(request: ModelRequest) -> str:
    ctx = request.runtime.context
    thread_id = getattr(ctx, "thread_id", None) or ""
    document_ids = getattr(ctx, "document_ids", None)
    user_id = get_user_id()

    # ── Memory context (cached per request) ────────────────────────────────────
    cached = getattr(ctx, "_memory_context", None)
    if cached is None:
        query = ""
        for msg in reversed(request.messages or []):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                query = content[:300]
                break
        try:
            from app.services.pdf_agent_memory import build_memory_context
            cached = await build_memory_context(
                agent_name=getattr(ctx, "agent_name", None) or "chat",
                thread_id=thread_id,
                user_id=user_id,
                query=query,
                document_ids=document_ids,
            )
        except Exception as exc:
            logger.debug("_memory_prompt: build failed: %s", exc)
            cached = {}
        if ctx is not None:
            try:
                ctx._memory_context = cached
            except Exception:
                pass

    parts: list[str] = []

    # ── Task prompt (stack contents injected at call time, not stored in state) ─
    task_prompt = getattr(ctx, "task_prompt", None)
    if task_prompt:
        prompts = task_prompt if isinstance(task_prompt, list) else [task_prompt]
        parts.extend(p for p in prompts if p)
    else:
        parts.append(SYSTEM_PROMPT)

    # ── Memory lines ────────────────────────────────────────────────────────────
    try:
        from app.services.pdf_agent_memory import format_memory_system_messages
        lines = format_memory_system_messages(cached)
        if lines:
            parts.extend(lines)
    except Exception as exc:
        logger.debug("_memory_prompt: format failed: %s", exc)

    # ── Document abstracts (cached per request, not stored in LangGraph state) ──
    if document_ids:
        abstracts_text = getattr(ctx, "_cached_abstracts_text", None)
        if abstracts_text is None:
            try:
                abstracts = await asyncio.to_thread(_get_abstracts, document_ids)
                if abstracts:
                    abstracts_text = (
                        "以下是本次對話引用的文件摘要，請以此作為背景資訊回答問題：\n\n"
                        + "\n\n".join(f"【{a['filename']}】\n{a['abstract']}" for a in abstracts)
                    )
                else:
                    abstracts_text = ""
            except Exception as exc:
                logger.debug("_memory_prompt: abstracts failed: %s", exc)
                abstracts_text = ""
            if ctx is not None:
                try:
                    ctx._cached_abstracts_text = abstracts_text
                except Exception:
                    pass
        if abstracts_text:
            parts.append(abstracts_text)

    return "\n\n".join(parts)


async def setup_checkpointer():
    """Initialize AsyncPostgresSaver, AsyncPostgresStore, and build the agent."""
    global _checkpointer, _store, _tool_agent, _tool_agent_mini, _pool
    from psycopg_pool import AsyncConnectionPool
    from langchain_openai import AzureOpenAIEmbeddings
    pool = AsyncConnectionPool(
        conninfo=pdf_settings.database_url,
        kwargs={
            "autocommit": True,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 5,
            "keepalives_count": 5,
        },
        min_size=1,
        max_size=10,
        # Recycle idle connections every 2 min, well below NeonDB's ~5-min timeout
        max_idle=120,
        # Ping with SELECT 1 before returning a connection; rebuilds dead ones
        check=AsyncConnectionPool.check_connection,
        reconnect_timeout=300,
        open=False,
    )
    await pool.open(wait=True)
    _pool = pool
    _checkpointer = AsyncPostgresSaver(
        pool,
        serde=JsonPlusSerializer(allowed_msgpack_modules=[
            ("app.agents.pdf.runner", "AgentResponse"),
        ]),
    )
    await _checkpointer.setup()

    _store = AsyncPostgresStore(
        pool,
        index={
            "embed": AzureOpenAIEmbeddings(
                azure_deployment=pdf_settings.azure_embedding_deployment,
                azure_endpoint=pdf_settings.azure_openai_endpoint,
                api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
                api_version=pdf_settings.azure_openai_api_version,
            ),
            "dims": 3072,
            "fields": ["$"],
        },
    )
    await _store.setup()

    def _make_agent(llm, tools):
        return create_agent(
            llm,
            tools=tools,
            middleware=[
                _memory_prompt,
                SummarizationMiddleware(
                    model=_get_mini_llm(),
                    trigger=("tokens", 8000),
                    keep=("messages", 10),
                ),
                ContextEditingMiddleware(
                    edits=[ClearToolUsesEdit(trigger=20000, keep=3)],
                ),
                _trim_messages,
                _track_model_cost,
                ModelCallLimitMiddleware(run_limit=15, exit_behavior="end"),
                ModelFallbackMiddleware(_get_mini_llm()),
                ModelRetryMiddleware(
                    max_retries=2,
                    retry_on=StructuredOutputValidationError,
                    on_failure="continue",
                ),
                ToolRetryMiddleware(
                    max_retries=2,
                    retry_on=(ConnectionError, TimeoutError),
                    on_failure="return_message",
                ),
            ],
            response_format=ProviderStrategy(AgentResponse, strict=True),
            checkpointer=_checkpointer,
            store=_store,
            context_schema=AgentContext,
        )

    _tool_agent = _make_agent(_get_agent_llm(), TOOLS)
    _tool_agent_mini = _make_agent(_get_mini_agent_llm(), TOOLS)


def _get_tool_agent(mini: bool = False):
    return _tool_agent_mini if mini else _tool_agent


def get_checkpointer() -> AsyncPostgresSaver | None:
    return _checkpointer


def get_store() -> AsyncPostgresStore | None:
    return _store


async def shutdown_checkpointer() -> None:
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:
            logger.warning("checkpointer pool close failed: %s", exc)
        _pool = None


async def get_pending_interrupt(thread_id: str) -> dict | None:
    if _checkpointer is None:
        return None
    try:
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = await _checkpointer.aget_tuple(config)
        if not checkpoint_tuple:
            return None
        snapshot_tasks = checkpoint_tuple.checkpoint.get("tasks") or []
        for task in snapshot_tasks:
            interrupts = getattr(task, "interrupts", None) or []
            if interrupts:
                return {"interrupt_id": str(task.id), "value": interrupts[0].value}
        for task_id, channel, value in (checkpoint_tuple.pending_writes or []):
            if channel == "__interrupt__":
                return {"interrupt_id": str(task_id), "value": value}
        return None
    except Exception as exc:
        logger.debug("get_pending_interrupt(%s): %s", thread_id, exc)
        return None


async def resume_from_interrupt(thread_id: str, response: str) -> bool:
    if _checkpointer is None:
        return False
    pending = await get_pending_interrupt(thread_id)
    if not pending:
        return False
    try:
        agent = _tool_agent
        if agent is None:
            return False
        config = {"configurable": {"thread_id": thread_id}}
        await agent.ainvoke(Command(resume=response), config)
        return True
    except Exception as exc:
        logger.warning("resume_from_interrupt(%s): %s", thread_id, exc)
        return False


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _extract_msg_data(chunk) -> tuple | None:
    """從各版本 astream chunk 中提取 (token_msg, meta) 二元組，不限制 node 名稱。"""
    # version="v2" dict format: {"type": "messages", "data": (msg, meta)}
    if isinstance(chunk, dict) and chunk.get("type") == "messages":
        data = chunk.get("data")
        if isinstance(data, tuple) and len(data) == 2:
            return data
    # older tuple format: ("messages", (msg, meta))
    if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] == "messages":
        data = chunk[1]
        if isinstance(data, tuple) and len(data) == 2:
            return data
    # bare tuple format from stream_mode="messages": (msg, meta)
    if isinstance(chunk, tuple) and len(chunk) == 2 and hasattr(chunk[0], "content"):
        return chunk
    return None


def _interrupts_from_chunk(chunk: dict) -> list | None:
    if chunk.get("type") != "updates":
        return None
    data = chunk.get("data")
    if not isinstance(data, dict):
        return None
    if "__interrupt__" in data:
        return data["__interrupt__"]
    for value in data.values():
        if isinstance(value, dict) and "__interrupt__" in value:
            return value["__interrupt__"]
    return None


def _resume_value(pending: dict | None, decisions: list[dict], interrupt_id: str | None = None) -> dict:
    resolved_interrupt_id = interrupt_id or (pending or {}).get("interrupt_id")
    if not resolved_interrupt_id:
        return {"decisions": decisions}
    return {resolved_interrupt_id: {"decisions": decisions}}


async def generate_title(messages: list[dict]) -> str:
    context = "\n".join(
        f"{m['role']}: {m['content'][:300]}" for m in messages[:4]
    )
    response = await _get_mini_llm().ainvoke([
        SystemMessage(content=(
            "根據以下對話內容，用繁體中文生成一個簡潔的對話標題（5-10字）。"
            "只回傳標題本身，不要加引號或其他說明。"
        )),
        HumanMessage(content=context),
    ])
    return response.content.strip()[:60]


async def get_thread_messages(thread_id: str) -> list[dict]:
    if _checkpointer is None:
        return []
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint_tuple = await _checkpointer.aget_tuple(config)
    if not checkpoint_tuple:
        return []
    messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": _content_to_text(msg.content)})
        elif isinstance(msg, AIMessage) and msg.content:
            result.append({"role": "assistant", "content": _extract_answer(_content_to_text(msg.content))})
    return result


async def _get_structured_response(thread_id: str) -> AgentResponse | None:
    if _checkpointer is None:
        return None
    checkpoint_tuple = await _checkpointer.aget_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if not checkpoint_tuple:
        return None
    return checkpoint_tuple.checkpoint.get("channel_values", {}).get("structured_response")


async def _build_messages(user_message: str) -> list:
    """Return only the current user message; system context is injected by _memory_prompt."""
    return [HumanMessage(content=user_message)]


async def run_tool_agent(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    metadata: dict | None = None,
    observation_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    task_prompt: str | list[str] | None = None,
    recursion_limit: int = 100,
    include_document_abstracts: bool = True,
    max_searches: int | None = None,
    max_consecutive_empty: int | None = None,
    use_mini: bool = False,
) -> tuple[str, list[str]]:
    import uuid as _uuid
    agent = _get_tool_agent(mini=use_mini)
    metadata = metadata or {}
    config: dict = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
        "metadata": metadata,
    }
    if observation_id:
        config["run_id"] = _uuid.UUID(observation_id)

    ctx = AgentContext(
        document_ids=document_ids,
        on_stage=on_stage,
        max_searches=max_searches,
        max_consecutive_empty=max_consecutive_empty,
        thread_id=thread_id,
        observation_id=observation_id,
        task_prompt=task_prompt,
    )
    result = await agent.ainvoke(
        {"messages": await _build_messages(user_message)},
        config,
        context=ctx,
    )

    structured: AgentResponse | None = result.get("structured_response")
    sources = ctx.tool_sources or (structured.sources if structured else [])
    if structured:
        return structured.answer, sources
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
    raw = ai_messages[-1].content if ai_messages else "Unable to generate a response."
    return _extract_answer(raw), []


def _extract_answer(content: str) -> str:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            answer = parsed.get("answer", "")
            if answer:
                return _strip_abstracts_block(str(answer))
    except Exception:
        pass

    last_answer: str | None = None
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(content):
        try:
            obj, end = decoder.raw_decode(content, idx)
            if isinstance(obj, dict) and obj.get("answer"):
                last_answer = str(obj["answer"])
            idx = end
        except Exception:
            idx += 1
    if last_answer is not None:
        return _strip_abstracts_block(last_answer)

    return _strip_abstracts_block(content)


def _strip_abstracts_block(text: str) -> str:
    if "<document_abstracts>" not in text:
        return text
    return re.sub(
        r"<document_abstracts>.*?</document_abstracts>\s*\n*",
        "",
        text,
        flags=re.DOTALL,
    ).lstrip()


async def run_tool_agent_stream(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    metadata: dict | None = None,
    observation_id: str | None = None,
    on_stage: Callable[[str], None] | None = None,
    task_prompt: str | list[str] | None = None,
    include_document_abstracts: bool = True,
    max_searches: int | None = None,
    max_consecutive_empty: int | None = None,
    use_mini: bool = False,
):
    """Async generator yielding (token, is_done, sources) tuples."""
    import uuid as _uuid
    agent = _get_tool_agent(mini=use_mini)
    metadata = metadata or {}
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 100,
        "metadata": metadata,
    }
    if observation_id:
        config["run_id"] = _uuid.UUID(observation_id)

    ctx = AgentContext(
        document_ids=document_ids,
        on_stage=on_stage,
        max_searches=max_searches,
        max_consecutive_empty=max_consecutive_empty,
        thread_id=thread_id,
        observation_id=observation_id,
        task_prompt=task_prompt,
    )

    init_messages = await _build_messages(user_message)

    async def _stream_chunks() -> AsyncIterator[dict]:
        async for chunk in agent.astream(
            {"messages": init_messages},
            config,
            context=ctx,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            yield chunk

    extractor = _AnswerExtractor()

    async for chunk in _stream_chunks():
        interrupts = _interrupts_from_chunk(chunk)
        if interrupts:
            yield interrupts, "interrupt", []
            return
        msg_data = _extract_msg_data(chunk)
        if msg_data is not None:
            token_msg, meta = msg_data
            text = _content_to_text(getattr(token_msg, "content", None))
            if text:
                answer_part = extractor.process(text)
                if answer_part:
                    yield answer_part, False, []

    structured = await _get_structured_response(thread_id)
    sources: list[str] = ctx.tool_sources or (structured.sources if structured else [])

    if not extractor.produced_output:
        answer: str = structured.answer if structured else ""
        if answer:
            chunk_size = 8
            for i in range(0, len(answer), chunk_size):
                yield answer[i:i + chunk_size], False, sources
                await asyncio.sleep(0)

    yield "", True, sources


async def run_tool_agent_resume_stream(
    thread_id: str,
    decisions: list[dict],
    *,
    interrupt_id: str | None = None,
    use_mini: bool = False,
) -> AsyncIterator[tuple[Any, bool | str, list[str]]]:
    agent = _get_tool_agent(mini=use_mini)
    if agent is None:
        return
    pending = await get_pending_interrupt(thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    extractor = _AnswerExtractor()
    async for chunk in agent.astream(
        Command(resume=_resume_value(pending, decisions, interrupt_id)),
        config,
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        interrupts = _interrupts_from_chunk(chunk)
        if interrupts:
            yield interrupts, "interrupt", []
            return
        msg_data = _extract_msg_data(chunk)
        if msg_data is not None:
            token_msg, meta = msg_data
            text = _content_to_text(getattr(token_msg, "content", None))
            if text:
                answer_part = extractor.process(text)
                if answer_part:
                    yield answer_part, False, []

    structured = await _get_structured_response(thread_id)
    sources: list[str] = structured.sources if structured else []

    if not extractor.produced_output:
        answer: str = structured.answer if structured else ""
        if answer:
            chunk_size = 8
            for i in range(0, len(answer), chunk_size):
                yield answer[i:i + chunk_size], False, sources
                await asyncio.sleep(0)
    yield "", True, sources
