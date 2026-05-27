"""Global concurrency gate for LLM-intensive operations."""
import asyncio

MAX_CONCURRENT = 2
_gate: asyncio.Semaphore | None = None


def get_gate() -> asyncio.Semaphore:
    global _gate
    if _gate is None:
        _gate = asyncio.Semaphore(MAX_CONCURRENT)
    return _gate
