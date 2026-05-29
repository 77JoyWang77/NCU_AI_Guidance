from app.utils import new_id
from collections.abc import AsyncIterator, Callable

from .runner import run_tool_agent as _run_agent
from .runner import run_tool_agent_stream as _run_agent_stream
from app.prompting.loader import load_stack

from .types import AgentLimitation, AgentResult, AgentStatus


async def _emit_stage(on_stage, msg: str) -> None:
    if not on_stage:
        return
    result = on_stage(msg)
    if hasattr(result, "__await__"):
        await result

STACK_NAME = "retrieval_default"
PROMPT_NAME = "retrieval_capability"
AGENT_NAME = "retrieval"


async def answer(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    task_prompt: str | list[str] | None = None,
    on_stage: Callable[[str], None] | None = None,
    recursion_limit: int = 30,
    metadata: dict[str, str | int] | None = None,
    observation_id: str | None = None,
    max_searches: int | None = None,
    max_consecutive_empty: int | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
) -> AgentResult:
    from datetime import datetime, timezone as _tz
    stack = load_stack(STACK_NAME)
    metadata = metadata or {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }

    observation_id = observation_id or new_id()
    await _emit_stage(on_stage, "搜尋相關段落中")

    effective_prompt = task_prompt if task_prompt is not None else stack.contents
    response, sources = await _run_agent(
        user_message,
        thread_id,
        document_ids,
        metadata=metadata,
        observation_id=observation_id,
        task_prompt=effective_prompt,
        on_stage=on_stage,
        recursion_limit=recursion_limit,
        max_searches=max_searches,
        max_consecutive_empty=max_consecutive_empty,
        use_mini=use_mini,
    )
    completed = bool(sources)
    return AgentResult(
        response=response,
        sources=sources,
        agent_name=metadata.get("agent_name", AGENT_NAME),
        prompt_name=metadata.get("prompt_name", PROMPT_NAME),
        prompt_version=metadata.get("prompt_version", "unknown"),
        observation_id=observation_id,
        status=AgentStatus(
            completed=completed,
            work_summary=f"從文件中搜尋相關內容，找到 {len(sources)} 個來源。" if completed else "搜尋文件但未找到相關內容。",
            gaps=[] if completed else ["未找到與問題相關的文件片段"],
            agent_limitation=AgentLimitation.NONE if completed else AgentLimitation.SINGLE_POINT_LOOKUP,
        ),
    )


async def stream(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    task_prompt: str | list[str] | None = None,
    on_stage: Callable[[str], None] | None = None,
    metadata: dict[str, str | int] | None = None,
    observation_id: str | None = None,
    trace_id: str | None = None,
    max_searches: int | None = None,
    max_consecutive_empty: int | None = None,
    use_mini: bool = False,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    stack = load_stack(STACK_NAME)
    metadata = metadata or {
        "agent_name": AGENT_NAME,
        **stack.metadata(),
    }

    observation_id = observation_id or new_id()
    await _emit_stage(on_stage, "搜尋相關段落中")

    effective_prompt = task_prompt if task_prompt is not None else stack.contents
    async for item in _run_agent_stream(
        user_message,
        thread_id,
        document_ids,
        metadata=metadata,
        task_prompt=effective_prompt,
        on_stage=on_stage,
        observation_id=observation_id,
        max_searches=max_searches,
        max_consecutive_empty=max_consecutive_empty,
        use_mini=use_mini,
    ):
        yield item
