"""Prompt registry — local-file only (no Langfuse)."""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
from dataclasses import dataclass

_PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts", "pdf"))
_EXTENDS_PREFIX = "# extends:"
_cache: dict[str, str] = {}
_hash_cache: dict[str, str] = {}
logger = logging.getLogger(__name__)


ALIASES: dict[str, str] = {
    "core": "core",
    "retrieval_capability": "retrieval_capability",
    "chat_mode": "chat_mode",
    "route_coordinator": "route_coordinator",
    "task_planner": "task_planner",
    "research_scheduler": "research_scheduler",
    "research_planner": "research_planner",
    "research_reflector": "research_reflector",
    "research_writer": "research_writer",
    "chat": "chat_mode",
    "router": "route_coordinator",
    "base_research": "retrieval_capability",
    "chat_task": "chat_mode",
}


@dataclass(frozen=True)
class PromptSpec:
    base_name: str
    name: str
    content: str
    version: str
    source_name: str
    langfuse_version: int | None = None


def canonical_name(name: str) -> str:
    return str(name).strip()


def source_name(name: str) -> str:
    prompt_name = canonical_name(name)
    return ALIASES.get(prompt_name, prompt_name)


def _path_for(name: str) -> str:
    return os.path.join(_PROMPTS_DIR, f"{source_name(name)}.txt")


def exists(name: str) -> bool:
    return os.path.exists(_path_for(name))


def _load_prompt(name: str, stack: list[str]) -> str:
    src = source_name(name)
    if src in stack:
        chain = " -> ".join([*stack, src])
        raise ValueError(f"Prompt extends cycle detected: {chain}")

    path = os.path.join(_PROMPTS_DIR, f"{src}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    if not lines:
        return content
    first = lines[0].strip()
    if not first.lower().startswith(_EXTENDS_PREFIX):
        return content

    parent = first[len(_EXTENDS_PREFIX):].strip()
    if not parent:
        raise ValueError(f"Prompt {src} has an empty extends target")
    body = "\n".join(lines[1:]).lstrip()
    return f"{_load_prompt(parent, [*stack, src]).rstrip()}\n\n{body}".rstrip() + "\n"


def get(name: str) -> str:
    src = source_name(name)
    if src not in _cache:
        _cache[src] = _load_prompt(src, [])
    return _cache[src]


def reload(name: str) -> str:
    src = source_name(name)
    _cache.pop(src, None)
    _hash_cache.pop(src, None)
    _ab_tests_cached.cache_clear()
    return get(name)


def reload_all() -> None:
    _cache.clear()
    _hash_cache.clear()
    _ab_tests_cached.cache_clear()


def version(name: str) -> str:
    src = source_name(name)
    get(name)
    if src not in _hash_cache:
        content = _cache.get(src, "")
        _hash_cache[src] = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{_hash_cache[src]}"


@functools.lru_cache(maxsize=8)
def _ab_tests_cached(raw: str) -> dict[str, list[str]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}

    result: dict[str, list[str]] = {}
    for base_name, variants in parsed.items():
        if isinstance(variants, str):
            names = [v.strip() for v in variants.split(",")]
        elif isinstance(variants, list):
            names = [str(v).strip() for v in variants]
        else:
            names = []
        valid = [name for name in names if name and exists(name)]
        if valid:
            key_names = {str(base_name)}
            base_source = source_name(str(base_name))
            for alias, src_name in ALIASES.items():
                if alias == base_name or src_name == base_source:
                    key_names.add(alias)
            for key_name in key_names:
                result[key_name] = valid
    return result


def _ab_tests() -> dict[str, list[str]]:
    return _ab_tests_cached(os.getenv("PROMPT_AB_TESTS", "").strip())


def select(name: str, key: str | None = None) -> str:
    variants = _ab_tests().get(name)
    if not variants:
        return name
    bucket_key = key or name
    digest = hashlib.sha256(f"{name}:{bucket_key}".encode("utf-8")).hexdigest()
    return variants[int(digest[:8], 16) % len(variants)]


def resolve(name: str, key: str | None = None) -> PromptSpec:
    base_name = canonical_name(name)
    active_name = select(base_name, key)
    src = source_name(active_name)
    return PromptSpec(
        base_name=base_name,
        name=active_name,
        content=get(active_name),
        version=version(active_name),
        source_name=src,
    )


def list_known_names() -> list[str]:
    file_names = []
    if os.path.isdir(_PROMPTS_DIR):
        file_names = [
            os.path.splitext(fname)[0]
            for fname in os.listdir(_PROMPTS_DIR)
            if fname.endswith(".txt")
        ]
    return sorted(set(file_names) | set(ALIASES))
