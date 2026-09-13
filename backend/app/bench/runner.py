"""Deterministic performance-policy benchmark harness.

Benchmarks run against synthetic fixtures, never personal data. They measure a
single wall-clock duration, record one privacy-safe ``benchmark`` diagnostics
event, and assert a documented threshold so a material regression fails loudly.
Threshold changes must be justified in the benchmark test, never silently edited.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.state.diagnostics import safe_record


def run_benchmark[T](
    name: str,
    threshold_ms: float,
    fn: Callable[[], T],
    *,
    baseline_ms: float | None = None,
    record: bool = True,
) -> tuple[T, float]:
    """Run one deterministic benchmark job and record its duration.

    Args:
        name: Benchmark identifier recorded in the diagnostics event.
        threshold_ms: Hard ceiling; the caller still asserts on the return.
        fn: Measured callable (no parameters).
        baseline_ms: Optional documented historical baseline for reporting.
        record: Whether to write a diagnostics event for this invocation.

    Returns:
        A tuple of the callable result and the elapsed duration in milliseconds.
    """
    started_at = time.perf_counter()
    result = fn()
    duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
    if record:
        safe_record(
            None,
            "benchmark",
            f"benchmark:{name}",
            duration_ms=duration_ms,
            status="ok" if duration_ms <= threshold_ms else "over_threshold",
            meta={
                "benchmark_name": name,
                "threshold_ms": str(round(threshold_ms, 3)),
                "baseline_ms": str(round(baseline_ms, 3)) if baseline_ms else "",
            },
        )
    return result, duration_ms


def best_of[T](runs: int, name: str, threshold_ms: float, fn: Callable[[], T]) -> tuple[T, float]:
    """Run a benchmark several times and keep the best (least noisy) result.

    Args:
        runs: Number of executions to time; the fastest is reported.
        name: Benchmark identifier.
        threshold_ms: Hard ceiling recorded for diagnostics.
        fn: The callable to time.

    Returns:
        A tuple of the fastest result object and its duration in milliseconds.
    """
    best_result: T | None = None
    best_ms = float("inf")
    for _ in range(runs):
        result, duration_ms = run_benchmark(name, threshold_ms, fn, record=False)
        if duration_ms < best_ms:
            best_result, best_ms = result, duration_ms
    if best_result is None:
        raise ValueError("best_of requires at least one run")
    safe_record(
        None,
        "benchmark",
        f"benchmark:{name}",
        duration_ms=best_ms,
        status="ok" if best_ms <= threshold_ms else "over_threshold",
        meta={
            "benchmark_name": name,
            "threshold_ms": str(round(threshold_ms, 3)),
            "baseline_ms": "",
        },
    )
    if best_ms > threshold_ms:
        raise AssertionError(
            f"Benchmark {name} exceeded threshold: {best_ms:.3f} ms > {threshold_ms:.3f} ms"
        )
    return best_result, best_ms
