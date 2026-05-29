"""Prompt stack loader."""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import registry

try:
    import tiktoken as _tiktoken
    _enc = _tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    def _count_tokens(text: str) -> int:
        return len(text) // 4


PROMPT_STACKS: dict[str, list[str]] = {
    "chat_default": ["core", "chat_mode"],
    "retrieval_default": ["core", "retrieval_capability"],
    "router_default": ["core", "route_coordinator"],
    "research_runtime": [
        "core",
        "task_planner",
        "research_scheduler",
        "research_planner",
        "research_reflector",
        "research_writer",
    ],
}

STACK_ALIASES: dict[str, str] = {}

PRIMARY_PROMPT_BY_STACK: dict[str, str] = {
    "chat_default": "chat_mode",
    "retrieval_default": "retrieval_capability",
    "router_default": "route_coordinator",
    "research_runtime": "research_writer",
}


@dataclass(frozen=True)
class PromptStack:
    name: str
    prompts: list[registry.PromptSpec]

    @property
    def contents(self) -> list[str]:
        return [prompt.content for prompt in self.prompts if prompt.content]

    @property
    def tokens_estimate(self) -> int:
        text = "\n".join(self.contents)
        if not text:
            return 0
        return max(1, _count_tokens(text))

    def metadata(self) -> dict[str, str | int]:
        prompts = [
            {
                "name": prompt.name,
                "base_name": prompt.base_name,
                "source_name": prompt.source_name,
                "version": prompt.version,
            }
            for prompt in self.prompts
        ]
        data: dict[str, str | int] = {
            "prompt_stack_name": self.name,
            "prompt_stack_json": json.dumps(prompts, ensure_ascii=False),
            "prompt_stack_tokens": self.tokens_estimate,
        }
        if self.prompts:
            primary_name = PRIMARY_PROMPT_BY_STACK.get(self.name)
            primary = next(
                (prompt for prompt in self.prompts if prompt.base_name == primary_name),
                self.prompts[-1],
            )
            data["base_prompt_name"] = self.prompts[0].name
            data["base_prompt_hash"] = self.prompts[0].version
            data["prompt_name"] = primary.name
            data["prompt_version"] = primary.version
            data["prompt_id"] = f"{primary.source_name}:{primary.version}"
            data["primary_prompt_json"] = json.dumps(
                {
                    "name": primary.name,
                    "base_name": primary.base_name,
                    "source_name": primary.source_name,
                    "version": primary.version,
                },
                ensure_ascii=False,
            )
            data["workflow_prompts_json"] = data["prompt_stack_json"]
        if len(self.prompts) >= 2:
            data["task_prompt_name"] = data["prompt_name"]
            data["task_prompt_hash"] = data["prompt_version"]
        return data


def load_stack(name: str, key: str | None = None) -> PromptStack:
    stack_name = STACK_ALIASES.get(name, name)
    if stack_name not in PROMPT_STACKS:
        raise KeyError(f"Unknown prompt stack: {name}")
    prompts = [registry.resolve(prompt_name, key) for prompt_name in PROMPT_STACKS[stack_name]]
    return PromptStack(name=stack_name, prompts=prompts)
