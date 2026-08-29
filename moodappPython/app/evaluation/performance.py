from __future__ import annotations

import asyncio
from statistics import mean
from time import perf_counter
from typing import Any
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..agents.orchestrator import Orchestrator
from ..schemas import OrchestrationRequest


class PerformanceSample(BaseModel):
    index: int
    latency_ms: int = Field(ge=0)
    succeeded: bool
    timed_out: bool = False
    trace_length: int = Field(default=0, ge=0)
    node_latency_ms: dict[str, int] = Field(default_factory=dict)
    model_name: str | None = None
    degraded: bool = False
    error: str | None = None


class PerformanceReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_requests: int
    successful_requests: int
    failed_requests: int
    concurrency: int
    duration_ms: int
    throughput_per_second: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: int
    timeout_rate: float
    degraded_request_rate: float
    node_p50_latency_ms: dict[str, float] = Field(default_factory=dict)
    node_p95_latency_ms: dict[str, float] = Field(default_factory=dict)
    samples: list[PerformanceSample] = Field(default_factory=list)


def _percentile(values: list[int], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile // 100
    return float(ordered[index])


async def run_performance_benchmark(
    orchestrator: Orchestrator,
    requests: list[OrchestrationRequest],
    *,
    concurrency: int = 4,
    timeout_seconds: float = 45.0,
) -> PerformanceReport:
    """Run concurrent orchestration requests and return report-ready latency metrics."""
    if not requests:
        raise ValueError("requests must not be empty")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    semaphore = asyncio.Semaphore(concurrency)
    started_all = perf_counter()

    async def run_one(index: int, request: OrchestrationRequest) -> PerformanceSample:
        async with semaphore:
            started = perf_counter()
            try:
                result = await asyncio.wait_for(
                    orchestrator.run(request), timeout=timeout_seconds
                )
                node_latency_ms: dict[str, int] = {}
                for event in getattr(result, "trace_events", []):
                    if event.duration_ms is not None:
                        node_latency_ms[event.agent] = int(event.duration_ms)
                    subagent_durations = event.metadata.get("subagent_duration_ms", {})
                    if isinstance(subagent_durations, dict):
                        for subagent, latency in subagent_durations.items():
                            node_latency_ms[f"{event.agent}.{subagent}"] = int(latency)
                return PerformanceSample(
                    index=index,
                    latency_ms=round((perf_counter() - started) * 1000),
                    succeeded=True,
                    trace_length=len(result.trace),
                    node_latency_ms=node_latency_ms,
                    model_name=getattr(result, "model", None),
                    degraded="fallback" in str(getattr(result, "model", "")).lower(),
                )
            except asyncio.TimeoutError:
                return PerformanceSample(
                    index=index,
                    latency_ms=round((perf_counter() - started) * 1000),
                    succeeded=False,
                    timed_out=True,
                    error="TimeoutError",
                )
            except Exception as exc:  # noqa: BLE001 - benchmark records failures.
                return PerformanceSample(
                    index=index,
                    latency_ms=round((perf_counter() - started) * 1000),
                    succeeded=False,
                    error=f"{type(exc).__name__}: {exc}",
                )

    samples = await asyncio.gather(
        *(run_one(index, request) for index, request in enumerate(requests))
    )
    duration_ms = round((perf_counter() - started_all) * 1000)
    latencies = [sample.latency_ms for sample in samples]
    successful = sum(1 for sample in samples if sample.succeeded)
    timed_out = sum(1 for sample in samples if sample.timed_out)
    degraded = sum(1 for sample in samples if sample.degraded)
    duration_seconds = max(duration_ms / 1000, 0.001)
    node_values: dict[str, list[int]] = {}
    for sample in samples:
        if not sample.succeeded:
            continue
        for node, latency in sample.node_latency_ms.items():
            node_values.setdefault(node, []).append(latency)
    return PerformanceReport(
        total_requests=len(samples),
        successful_requests=successful,
        failed_requests=len(samples) - successful,
        concurrency=concurrency,
        duration_ms=duration_ms,
        throughput_per_second=round(len(samples) / duration_seconds, 3),
        average_latency_ms=round(mean(latencies), 2),
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        max_latency_ms=max(latencies),
        timeout_rate=round(timed_out / len(samples), 4),
        degraded_request_rate=round(degraded / len(samples), 4),
        node_p50_latency_ms={
            node: _percentile(values, 50) for node, values in sorted(node_values.items())
        },
        node_p95_latency_ms={
            node: _percentile(values, 95) for node, values in sorted(node_values.items())
        },
        samples=samples,
    )


def report_to_dict(report: PerformanceReport) -> dict[str, Any]:
    """Keep the performance result compatible with the evaluation JSON reports."""
    return report.model_dump(mode="json")
