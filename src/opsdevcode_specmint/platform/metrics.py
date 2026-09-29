"""In-memory platform metrics hooks. No Mint source in log payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any


@dataclass
class PlatformMetrics:
    lifecycle_outcomes: dict[str, int] = field(default_factory=dict)
    lifecycle_latency_ms: dict[str, list[float]] = field(default_factory=dict)

    def record_lifecycle(self, outcome: str, *, latency_ms: float | None = None) -> None:
        self.lifecycle_outcomes[outcome] = self.lifecycle_outcomes.get(outcome, 0) + 1
        if latency_ms is not None:
            bucket = self.lifecycle_latency_ms.setdefault(outcome, [])
            bucket.append(latency_ms)

    def snapshot(self) -> dict[str, Any]:
        latency: dict[str, dict[str, float]] = {}
        for key, samples in self.lifecycle_latency_ms.items():
            if not samples:
                continue
            latency[key] = {
                "count": float(len(samples)),
                "sumMs": float(sum(samples)),
            }
        return {"lifecycleOutcomes": dict(self.lifecycle_outcomes), "lifecycleLatency": latency}


_METRICS = PlatformMetrics()


def platform_metrics() -> PlatformMetrics:
    return _METRICS


class LifecycleTimer:
    def __init__(self, outcome: str) -> None:
        self._outcome = outcome
        self._start = perf_counter()

    def finish(self) -> None:
        elapsed_ms = (perf_counter() - self._start) * 1000.0
        _METRICS.record_lifecycle(self._outcome, latency_ms=elapsed_ms)
