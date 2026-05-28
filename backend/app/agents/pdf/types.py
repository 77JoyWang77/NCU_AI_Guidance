from dataclasses import dataclass, field
from enum import Enum


class AgentLimitation(str, Enum):
    NONE = ""
    CONTEXT_INSUFFICIENT = "context_insufficient"
    SINGLE_POINT_LOOKUP = "single_point_lookup"
    RESEARCH_BUDGET_EXHAUSTED = "research_budget_exhausted"


@dataclass(frozen=True)
class AgentStatus:
    """Self-assessment returned by each agent to inform router decisions."""
    completed: bool = True
    work_summary: str = ""
    gaps: list[str] = field(default_factory=list)
    agent_limitation: AgentLimitation = AgentLimitation.NONE


@dataclass(frozen=True)
class AgentRoute:
    agent_name: str
    prompt_name: str
    prompt_version: str = "unknown"
    compose_after: bool = False
    evaluate_after: bool = False


@dataclass(frozen=True)
class AgentResult:
    response: str
    sources: list[str] = field(default_factory=list)
    agent_name: str = "chat"
    prompt_name: str = "chat"
    prompt_version: str = "unknown"
    observation_id: str | None = None
    status: AgentStatus = field(default_factory=AgentStatus)
    coverage_result: dict | None = None
