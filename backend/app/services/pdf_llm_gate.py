"""Global concurrency gate for LLM-intensive operations."""
import asyncio

MAX_CONCURRENT = 2
_gate: asyncio.Semaphore | None = None


def get_gate() -> asyncio.Semaphore:
    global _gate
    if _gate is None:
        _gate = asyncio.Semaphore(MAX_CONCURRENT)
    return _gate


async def acquire_with_timeout(timeout: float = 30.0) -> bool:
    """Try to acquire the gate semaphore within `timeout` seconds.

    Returns True if acquired, False on timeout (semaphore is NOT held).
    """
    try:
        await asyncio.wait_for(get_gate().acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
