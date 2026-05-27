from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentStatus:
    """Self-assessment returned by each agent to inform router decisions."""
    completed: bool = True
    work_summary: str = ""
    gaps: list[str] = field(default_factory=list)
    agent_limitation: str = ""


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
