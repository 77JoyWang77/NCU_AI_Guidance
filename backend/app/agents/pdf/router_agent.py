from app.utils import new_id
from collections.abc import AsyncIterator
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from app.pdf_config import pdf_settings
from app.prompting.loader import load_stack
from app.prompting.registry import get as get_prompt
from app.prompting.registry import version as prompt_version

from .types import AgentRoute, AgentResult, AgentStatus
from .request_context import get_user_id
from . import steering as _steering

logger = logging.getLogger(__name__)


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    task.add_done_callback(
        lambda t: logger.warning("Background task failed: %s", t.exception())
        if not t.cancelled() and t.exception()
        else None
    )


ROUTER_PROMPT_NAME = "route_coordinator"
VALID_AGENTS = {"chat", "retrieval", "research", "question", "evaluation"}
MAX_HANDOFFS = 3

_FOLLOWUP_SIGNALS = (
    "繼續", "再說", "補充", "更多", "詳細", "展開", "那", "那麼", "這個",
    "剛才", "你說的", "上面", "除此之外", "另外", "而且", "還有",
    "more", "continue", "elaborate", "expand", "follow up",
)


def _looks_like_followup(message: str) -> bool:
    text = (message or "").strip()
    if len(text) > 60:
        return False
    lower = text.lower()
    return any(sig in lower for sig in _FOLLOWUP_SIGNALS)


class RouterDecision(BaseModel):
    agent_name: str = Field(
        description="Exact agent to invoke: chat | retrieval | research | question | evaluation"
    )
    evaluate_after: bool = Field(default=False)
    reason: str = Field(default="")


@dataclass(frozen=True)
class ExecutionStep:
    agent_name: str
    observation_id: str
    trace_id: str
    kind: str = "primary"
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    trace_id: str
    route: AgentRoute
    steps: tuple[ExecutionStep, ...]
    evaluate_after: bool = False

    @property
    def primary_step(self) -> ExecutionStep:
        return self.steps[0]

    @property
    def composition_step(self) -> ExecutionStep | None:
        return next((step for step in self.steps if step.kind == "composition"), None)

    @property
    def evidence_step(self) -> ExecutionStep | None:
        return next((step for step in self.steps if step.kind == "evidence_collection"), None)

    @property
    def target_step(self) -> ExecutionStep:
        return next((step for step in self.steps if step.kind == "primary"), self.steps[0])


def _prompt_key(thread_id: str | None, document_ids: list[int] | None) -> str:
    doc_key = ",".join(str(doc_id) for doc_id in sorted(document_ids or []))
    return f"{thread_id or ''}:{doc_key}"


async def _escalation_route_for(
    result: AgentResult,
    route: AgentRoute,
    user_message: str,
    document_ids: list[int] | None,
    thread_id: str | None,
    hop_count: int,
    visited_agents: frozenset[str],
) -> AgentRoute | None:
    if result.status.completed or not document_ids or hop_count + 1 >= MAX_HANDOFFS:
        return None
    guidance = _steering.get_and_clear(thread_id) if thread_id else None
    decision = await _orchestrate(
        user_message,
        has_docs=True,
        document_ids=document_ids,
        previous_agent=route.agent_name,
        agent_status=result.status,
        steering_guidance=guidance,
    )
    if decision.agent_name == route.agent_name or decision.agent_name in visited_agents:
        return None
    return _route_for_agent(
        decision.agent_name, document_ids, thread_id, evaluate_after=decision.evaluate_after
    )


def _allows_background_evaluation(agent_name: str, has_docs: bool) -> bool:
    return has_docs and agent_name in {"research", "retrieval", "question"}


def _normalise_decision(decision: RouterDecision, has_docs: bool) -> RouterDecision:
    agent_name = decision.agent_name if decision.agent_name in VALID_AGENTS else "chat"
    if agent_name in {"research", "retrieval"} and not has_docs:
        agent_name = "chat"
    evaluate_after = bool(decision.evaluate_after and _allows_background_evaluation(agent_name, has_docs))
    return RouterDecision(agent_name=agent_name, evaluate_after=evaluate_after, reason=decision.reason)


def _primary_prompt(stack_name: str, base_name: str, thread_id: str | None, document_ids: list[int] | None):
    stack = load_stack(stack_name, _prompt_key(thread_id, document_ids))
    return next((p for p in stack.prompts if p.base_name == base_name), stack.prompts[-1])


def _route_for_agent(
    agent_name: str,
    document_ids: list[int] | None = None,
    thread_id: str | None = None,
    *,
    evaluate_after: bool = False,
) -> AgentRoute:
    if agent_name not in VALID_AGENTS:
        agent_name = "chat"
    if agent_name == "research":
        prompt = _primary_prompt("research_runtime", "research_writer", thread_id, document_ids)
        return AgentRoute(agent_name, prompt.name, prompt.version, compose_after=False, evaluate_after=evaluate_after)
    if agent_name == "question":
        return AgentRoute(agent_name, "question_skill", prompt_version("question_skill"), compose_after=False, evaluate_after=evaluate_after)
    if agent_name == "retrieval":
        return AgentRoute(agent_name, "retrieval_capability", prompt_version("retrieval_capability"), compose_after=False, evaluate_after=evaluate_after)
    if agent_name == "evaluation":
        return AgentRoute(agent_name, "evaluation_agent", prompt_version("evaluation_agent"), evaluate_after=False)
    return AgentRoute("chat", "chat_mode", prompt_version("chat_mode"), evaluate_after=False)


def _fetch_document_context(document_ids: list[int]) -> list[dict]:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfDocument
    with PdfSessionLocal() as db:
        docs = (
            db.query(PdfDocument.id, PdfDocument.filename, PdfDocument.abstract_text)
            .filter(PdfDocument.id.in_(document_ids))
            .all()
        )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "abstract": (d.abstract_text or "")[:600],
        }
        for d in docs
    ]


def _build_execution_plan(
    route: AgentRoute,
    *,
    trace_id: str,
    observation_id: str | None = None,
    collect_evidence: bool = False,
) -> ExecutionPlan:
    agent_name = route.agent_name
    steps: list[ExecutionStep] = []
    if collect_evidence and agent_name == "question":
        steps.append(ExecutionStep(
            agent_name="retrieval",
            observation_id=new_id(),
            trace_id=trace_id,
            kind="evidence_collection",
            reason="question_requires_document_evidence",
        ))
    steps.append(ExecutionStep(
        agent_name=agent_name,
        observation_id=observation_id or new_id(),
        trace_id=trace_id,
        kind="primary",
        reason=f"agent={agent_name}",
    ))
    if route.compose_after and agent_name not in {"chat", "evaluation"}:
        steps.append(ExecutionStep(
            agent_name="chat",
            observation_id=new_id(),
            trace_id=trace_id,
            kind="composition",
            reason="final_composition",
        ))
    return ExecutionPlan(
        trace_id=trace_id,
        route=route,
        steps=tuple(steps),
        evaluate_after=route.evaluate_after,
    )


_router_llm = None


def _get_router_llm():
    global _router_llm
    if _router_llm is None:
        _router_llm = AzureChatOpenAI(
            azure_deployment=pdf_settings.azure_mini_deployment or pdf_settings.azure_chat_deployment,
            azure_endpoint=pdf_settings.azure_openai_endpoint,
            api_key=pdf_settings.azure_openai_api_key.get_secret_value(),
            api_version=pdf_settings.azure_openai_api_version,
            temperature=0,
        )
    return _router_llm


async def _orchestrate(
    message: str,
    has_docs: bool,
    document_ids: list[int] | None = None,
    previous_agent: str | None = None,
    is_followup: bool = False,
    agent_status: AgentStatus | None = None,
    steering_guidance: str | None = None,
) -> RouterDecision:
    stack = load_stack("router_default")
    system = get_prompt(ROUTER_PROMPT_NAME)

    doc_context: list[dict] = []
    if has_docs and document_ids:
        doc_context = await asyncio.to_thread(_fetch_document_context, document_ids)

    user = {
        "message": message,
        "has_documents": has_docs,
        "document_context": doc_context,
        "previous_agent": previous_agent,
        "is_followup_signal": is_followup,
        "agent_status": {
            "completed": agent_status.completed,
            "work_summary": agent_status.work_summary,
            "gaps": agent_status.gaps,
            "agent_limitation": agent_status.agent_limitation,
        } if agent_status else None,
        "steering_guidance": steering_guidance,
        "available_agents": ["chat", "retrieval", "research", "question", "evaluation"],
        "response_format": {
            "agent_name": "chat|retrieval|research|question|evaluation",
            "evaluate_after": "boolean",
            "reason": "short reason",
        },
    }
    try:
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system),
            ("human", "{payload}"),
        ])
        structured = _get_router_llm().with_structured_output(RouterDecision)
        chain = prompt | structured
        decision: RouterDecision = await chain.ainvoke(
            {"payload": json.dumps(user, ensure_ascii=False)}
        )
        return _normalise_decision(decision, has_docs)
    except Exception as exc:
        logger.warning("Orchestrator LLM failed; using conservative fallback: %s", exc)
        fallback = "retrieval" if has_docs else "chat"
        return RouterDecision(agent_name=fallback, evaluate_after=False, reason="fallback")


async def route_request(
    message: str,
    document_ids: list[int] | None = None,
    thread_id: str | None = None,
    previous_agent_name: str | None = None,
) -> AgentRoute:
    has_docs = bool(document_ids)
    is_followup = _looks_like_followup(message)
    decision = await _orchestrate(
        message,
        has_docs,
        document_ids,
        previous_agent=previous_agent_name,
        is_followup=is_followup,
    )
    return _route_for_agent(
        decision.agent_name, document_ids, thread_id, evaluate_after=decision.evaluate_after
    )


async def _update_memory(
    agent_name: str,
    thread_id: str,
    user_id: str | None,
    document_ids: list[int] | None,
    question: str,
    result,
) -> None:
    from app.services.pdf_agent_memory import record_agent_memory
    await record_agent_memory(
        agent_name=agent_name,
        thread_id=thread_id,
        user_id=user_id,
        question=question,
        result=result,
        document_ids=document_ids,
    )


async def _run_evaluation_agent(
    thread_id: str,
    *,
    observation_id: str | None = None,
    trace_id: str | None = None,
    exclude_observation_id: str | None = None,
    answer: str | None = None,
    sources: list[str] | None = None,
    user_message: str | None = None,
    agent_name: str = "chat",
) -> AgentResult:
    from app.agents.pdf.evaluation_agent import (
        evaluate_direct_answer,
        evaluate_latest_thread_message,
        format_evaluation_for_user,
    )
    if answer is not None:
        result = await evaluate_direct_answer(
            user_task=user_message or "",
            answer=answer,
            sources=sources or [],
            agent_name=agent_name,
        )
    else:
        result = await evaluate_latest_thread_message(
            thread_id,
            exclude_observation_id=exclude_observation_id,
        )
    return AgentResult(
        response=format_evaluation_for_user(result),
        sources=[],
        agent_name="evaluation",
        prompt_name="evaluation_agent",
        prompt_version=prompt_version("evaluation_agent"),
        observation_id=observation_id,
        status=AgentStatus(completed=True, work_summary="完成品質評估。"),
    )


async def run_research_agent(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None,
    *,
    observation_id: str | None,
    trace_id: str | None = None,
    on_stage=None,
    on_token=None,
    bypass_cache: bool = False,
) -> AgentResult:
    from .research import run_research_task

    stack = load_stack("research_runtime", _prompt_key(thread_id, document_ids))
    metadata = {
        "agent_name": "research",
        **stack.metadata(),
    }
    return await run_research_task(
        question=user_message,
        thread_id=thread_id,
        document_ids=document_ids or [],
        research_mode="research",
        metadata=metadata,
        observation_id=observation_id,
        on_stage=on_stage,
        on_token=on_token,
        max_searches=20,
        max_searches_per_slot=3,
        max_consecutive_no_new=2,
        trace_id=trace_id,
        bypass_cache=bypass_cache,
    )


async def run_chat_agent(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None,
    *,
    observation_id: str | None,
    trace_id: str | None = None,
    on_stage=None,
    use_mini: bool = False,
) -> AgentResult:
    from .chat_agent import answer as _chat_answer
    return await _chat_answer(
        user_message,
        thread_id,
        document_ids,
        observation_id=observation_id,
        trace_id=trace_id,
        on_stage=on_stage,
        use_mini=use_mini,
    )


async def route_agent_message(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    route: AgentRoute | None = None,
    trace_id: str | None = None,
    use_mini: bool = False,
) -> AgentResult:
    """Route a user message to the appropriate task agent (loop, not recursion)."""
    from . import chat_agent, question_agent, retrieval_agent

    trace_id = trace_id or new_id()
    _visited: frozenset[str] = frozenset()
    _hop = 0
    plan: "ExecutionPlan | None" = None
    current_route: AgentRoute | None = None
    result: AgentResult | None = None
    next_route: AgentRoute | None = route

    while _hop < MAX_HANDOFFS:

        if next_route is not None:
            current_route = next_route
            next_route = None
        else:
            current_route = await route_request(user_message, document_ids, thread_id)

        plan = _build_execution_plan(
            current_route,
            trace_id=trace_id,
            collect_evidence=bool(document_ids) and current_route.agent_name == "question",
        )
        step = plan.target_step

        try:
            if current_route.agent_name == "evaluation":
                result = await _run_evaluation_agent(
                    thread_id,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                )
                return result

            elif current_route.agent_name == "research":
                result = await run_research_agent(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                )
                _fire_and_forget(_update_memory(
                    "research", thread_id, get_user_id(), document_ids, user_message, result
                ))

            elif current_route.agent_name == "question":
                evidence_context = None
                evidence_sources: list[str] = []
                evidence_step = plan.evidence_step
                if evidence_step is not None:
                    evidence = await retrieval_agent.answer(
                        user_message, thread_id, document_ids,
                        observation_id=evidence_step.observation_id,
                        trace_id=evidence_step.trace_id,
                        use_mini=use_mini,
                    )
                    evidence_context = evidence.response
                    evidence_sources = evidence.sources
                result = await question_agent.answer(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    use_mini=use_mini,
                    evidence_context=evidence_context,
                    evidence_sources=evidence_sources,
                )

            elif current_route.agent_name == "retrieval":
                result = await retrieval_agent.answer(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    use_mini=use_mini,
                )

            else:  # chat
                result = await chat_agent.answer(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    use_mini=use_mini,
                )

        except Exception:
            raise

        if (result is not None
                and not result.status.completed
                and document_ids
                and _hop + 1 < MAX_HANDOFFS):
            _esc = await _escalation_route_for(
                result, current_route, user_message, document_ids, thread_id,
                _hop, _visited | {current_route.agent_name},
            )
            if _esc is not None:
                _visited = _visited | {current_route.agent_name}
                next_route = _esc
                _hop += 1
                continue

        break

    if plan is not None and current_route is not None and result is not None:
        await _finalize_plan(
            plan, current_route, thread_id, document_ids, user_message,
            output_response=result.response,
            primary_observation_id=result.observation_id,
            sources=result.sources,
            result=result,
        )
        result = await _run_composition(plan, result, user_message, thread_id, document_ids, use_mini)

    return result


async def _write_agent_message(
    *,
    thread_id: str,
    user_message: str,
    output_response: str,
    sources: list[str],
    route: AgentRoute,
    primary_observation_id: str,
    result: AgentResult | None,
) -> None:
    from app.database_pdf import PdfSessionLocal
    from app.models.pdf_models import PdfAgentMessage
    msg = PdfAgentMessage(
        message_id=new_id(),
        thread_id=thread_id,
        user_id=get_user_id(),
        agent_name=route.agent_name,
        user_question=user_message,
        agent_answer=output_response,
        sources=sources,
        trace_summary=result.coverage_result if result else None,
        observation_id=primary_observation_id,
    )
    def _write():
        with PdfSessionLocal() as db:
            db.add(msg)
            db.commit()
    try:
        await asyncio.to_thread(_write)
    except Exception as exc:
        logger.warning("_write_agent_message failed thread=%s: %s", thread_id, exc)


async def _finalize_plan(
    plan: ExecutionPlan,
    route: AgentRoute,
    thread_id: str,
    document_ids: list[int] | None,
    user_message: str,
    *,
    output_response: str | None,
    primary_observation_id: str,
    sources: list[str] | None = None,
    result: AgentResult | None = None,
) -> None:
    if thread_id and output_response:
        _fire_and_forget(_write_agent_message(
            thread_id=thread_id,
            user_message=user_message,
            output_response=output_response,
            sources=sources or [],
            route=route,
            primary_observation_id=primary_observation_id,
            result=result,
        ))
    if plan.evaluate_after:
        _fire_and_forget(_run_evaluation_agent(
            thread_id,
            trace_id=plan.trace_id,
            exclude_observation_id=primary_observation_id,
            answer=output_response,
            sources=sources or [],
            user_message=user_message,
            agent_name=route.agent_name,
        ))
    if route.agent_name == "research" and result is not None:
        _fire_and_forget(_update_memory(
            "research", thread_id, get_user_id(), document_ids, user_message, result
        ))


async def _run_composition(
    plan: ExecutionPlan,
    result: AgentResult,
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None,
    use_mini: bool,
) -> AgentResult:
    composition_step = plan.composition_step
    if composition_step is None:
        return result
    from . import chat_agent
    return await chat_agent.compose_final_response(
        user_message=user_message,
        task_result=result,
        thread_id=thread_id,
        document_ids=document_ids,
        observation_id=composition_step.observation_id,
        trace_id=composition_step.trace_id,
        use_mini=use_mini,
    )


_AGENT_STAGE_LABELS: dict[str, str] = {
    "chat":       "直接回答中",
    "retrieval":  "搜尋文件中",
    "question":   "生成導讀問題中",
    "evaluation": "品質評估中",
}


async def route_agent_stream(
    user_message: str,
    thread_id: str,
    document_ids: list[int] | None = None,
    *,
    route: AgentRoute | None = None,
    trace_id: str | None = None,
    observation_id: str | None = None,
    on_stage=None,
    on_route=None,
    previous_agent_name: str | None = None,
    bypass_cache: bool = False,
    use_mini: bool = False,
) -> AsyncIterator[tuple[str, bool, list[str]]]:
    """Stream tokens. Multi-hop routing handled via while-loop (not recursion)."""
    from . import chat_agent, question_agent, retrieval_agent

    trace_id = trace_id or new_id()
    _visited: frozenset[str] = frozenset()
    _full_response: str | None = None
    last_sources: list[str] = []
    plan: "ExecutionPlan | None" = None
    step = None
    current_route: AgentRoute | None = None
    _hop = 0
    next_route: AgentRoute | None = route

    while _hop < MAX_HANDOFFS:

        from . import chat_jobs as _chat_jobs
        if _chat_jobs.is_cancelled(thread_id):
            logger.info("route_agent_stream cancelled thread_id=%s", thread_id)
            yield "", True, last_sources
            return

        if next_route is not None:
            current_route = next_route
            next_route = None
        else:
            current_route = await route_request(
                user_message, document_ids, thread_id,
                previous_agent_name=previous_agent_name if _hop == 0 else None,
            )

        if on_route and _hop == 0:
            on_route(current_route)
        if on_stage and current_route.agent_name in _AGENT_STAGE_LABELS:
            on_stage(_AGENT_STAGE_LABELS[current_route.agent_name])

        plan = _build_execution_plan(
            current_route,
            trace_id=trace_id,
            observation_id=observation_id if _hop == 0 else None,
        )
        step = plan.target_step

        if current_route.agent_name == "evaluation":
            result = await _run_evaluation_agent(
                thread_id,
                observation_id=step.observation_id,
                trace_id=step.trace_id,
            )
            yield result.response, False, []
            yield "", True, []
            return

        _streamed_response: list[str] = []
        agent_result: AgentResult | None = None

        try:
            if current_route.agent_name == "research":
                _rqueue: asyncio.Queue = asyncio.Queue()

                def _push_research_token(t: str) -> None:
                    _rqueue.put_nowait(("token", t))

                def _push_research_stage(msg: str) -> None:
                    if on_stage:
                        on_stage(msg)

                rtask = asyncio.create_task(
                    run_research_agent(
                        user_message, thread_id, document_ids,
                        observation_id=step.observation_id,
                        trace_id=step.trace_id,
                        on_stage=_push_research_stage,
                        on_token=_push_research_token,
                        bypass_cache=bypass_cache,
                    )
                )
                rtask.add_done_callback(lambda _: _rqueue.put_nowait(None))

                streamed_tokens = False
                while True:
                    event = await _rqueue.get()
                    if event is None:
                        while not _rqueue.empty():
                            rem = _rqueue.get_nowait()
                            if rem is None:
                                continue
                            etype, val = rem
                            if etype == "token":
                                _streamed_response.append(val)
                                if plan.composition_step is None:
                                    yield val, False, []
                                streamed_tokens = True
                        break
                    etype, val = event
                    if etype == "token":
                        _streamed_response.append(val)
                        if plan.composition_step is None:
                            yield val, False, []
                        streamed_tokens = True

                if rtask.cancelled():
                    raise asyncio.CancelledError("research task was cancelled")
                if rtask.exception():
                    raise rtask.exception()
                research_result = rtask.result()
                if not streamed_tokens:
                    _streamed_response.append(research_result.response)
                    if plan.composition_step is None:
                        chunk_size = 8
                        for _i in range(0, len(research_result.response), chunk_size):
                            yield research_result.response[_i:_i + chunk_size], False, []
                            await asyncio.sleep(0)
                _fire_and_forget(_update_memory(
                    "research", thread_id, get_user_id(), document_ids, user_message, research_result
                ))
                last_sources = research_result.sources
                agent_result = research_result

            elif current_route.agent_name == "question":
                evidence_context = None
                evidence_sources: list[str] = []
                evidence_step = plan.evidence_step
                if evidence_step is not None:
                    evidence = await retrieval_agent.answer(
                        user_message, thread_id, document_ids,
                        observation_id=evidence_step.observation_id,
                        trace_id=evidence_step.trace_id,
                        on_stage=on_stage,
                        use_mini=use_mini,
                    )
                    evidence_context = evidence.response
                    evidence_sources = evidence.sources
                async for item in question_agent.stream(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    on_stage=on_stage,
                    use_mini=use_mini,
                    evidence_context=evidence_context,
                    evidence_sources=evidence_sources,
                ):
                    token, is_done, sources = item
                    if is_done == "interrupt":
                        yield item
                        return
                    if is_done:
                        last_sources = sources
                    else:
                        _streamed_response.append(token)
                        if plan.composition_step is None:
                            yield item

            elif current_route.agent_name == "retrieval":
                _retrieval_response = ""
                _retrieval_sources: list[str] = []
                async for _item in retrieval_agent.stream(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    on_stage=on_stage,
                    use_mini=use_mini,
                ):
                    _tok, _done, _src = _item
                    if _done:
                        _retrieval_sources = _src
                    else:
                        _retrieval_response += _tok
                        _streamed_response.append(_tok)
                        if plan.composition_step is None:
                            yield _item

                last_sources = _retrieval_sources
                _retrieval_has_answer = bool(_retrieval_response)
                agent_result = AgentResult(
                    response=_retrieval_response,
                    sources=_retrieval_sources,
                    agent_name="retrieval",
                    status=AgentStatus(
                        completed=_retrieval_has_answer,
                        gaps=[] if _retrieval_has_answer else ["未找到與問題相關的文件片段"],
                        agent_limitation="" if _retrieval_has_answer else "單點查找，文件中可能無此資訊",
                    ),
                )

            else:  # chat
                async for item in chat_agent.stream(
                    user_message, thread_id, document_ids,
                    observation_id=step.observation_id,
                    trace_id=step.trace_id,
                    on_stage=on_stage,
                    use_mini=use_mini,
                ):
                    token, is_done, sources = item
                    if is_done == "interrupt":
                        yield item
                        return
                    if is_done:
                        last_sources = sources
                    else:
                        _streamed_response.append(token)
                        yield item

                _chat_full = "".join(_streamed_response)
                if "[INSUFFICIENT_CONTEXT]" in _chat_full:
                    _chat_full = _chat_full.replace("[INSUFFICIENT_CONTEXT]", "").strip()
                    _streamed_response = [_chat_full]
                    agent_result = AgentResult(
                        response=_chat_full,
                        sources=last_sources,
                        agent_name="chat",
                        status=AgentStatus(
                            completed=False,
                            work_summary="chat 無法從現有 context 充分回答",
                            agent_limitation="chat 無文件搜尋工具，context 不足以充分回答此問題",
                        ),
                    )

        except Exception:
            raise

        _full_response = "".join(_streamed_response) or None

        if plan.composition_step is not None:
            if on_stage:
                on_stage("組織回答中")
            _composed = await _run_composition(
                plan,
                AgentResult(response=_full_response or "", sources=last_sources,
                            agent_name=current_route.agent_name),
                user_message, thread_id, document_ids, use_mini,
            )
            yield _composed.response, False, _composed.sources
            last_sources = _composed.sources
            _full_response = _composed.response

        if (agent_result is not None
                and not agent_result.status.completed
                and document_ids
                and _hop + 1 < MAX_HANDOFFS):
            _esc = await _escalation_route_for(
                agent_result, current_route, user_message, document_ids, thread_id,
                _hop, _visited | {current_route.agent_name},
            )
            if _esc is not None:
                _visited = _visited | {current_route.agent_name}
                next_route = _esc
                _hop += 1
                continue

        break

    if plan is not None and step is not None and current_route is not None:
        await _finalize_plan(
            plan, current_route, thread_id, document_ids, user_message,
            output_response=_full_response,
            primary_observation_id=step.observation_id,
            sources=last_sources,
        )

    yield "", True, last_sources
