"""
latency_store.py

In-process ring buffer for API request latency tracking.
純標準庫，不 import 任何 app.* 模組，避免 circular import。
"""

from collections import defaultdict, deque
import statistics
import time

_START_TIME: float = time.time()


def get_server_uptime_seconds() -> int:
    return int(time.time() - _START_TIME)

_records: deque[dict] = deque(maxlen=500)


def record_request(endpoint: str, ms: float, status: int) -> None:
    _records.append({"endpoint": endpoint, "ms": ms, "status": status, "ts": time.time()})


def get_latency_stats() -> list[dict]:
    """回傳各 endpoint 的 avg_ms、p95_ms、error_count（從 deque 即時計算）。"""
    groups: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    for r in _records:
        groups[r["endpoint"]].append(r["ms"])
        if r["status"] >= 500:
            errors[r["endpoint"]] += 1

    result = []
    for ep, ms_list in groups.items():
        sorted_ms = sorted(ms_list)
        n = len(sorted_ms)
        p95_idx = max(0, int(n * 0.95) - 1)
        result.append({
            "endpoint":        ep,
            "count":           n,
            "avg_ms":          round(statistics.mean(ms_list), 1),
            "p95_ms":          round(sorted_ms[p95_idx], 1),
            "error_count":     errors[ep],
            "error_rate_pct":  round(errors[ep] / n * 100, 1),
        })
    return sorted(result, key=lambda x: -x["avg_ms"])
