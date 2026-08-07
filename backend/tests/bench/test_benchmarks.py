"""Deterministic performance-policy benchmarks on synthetic data.

Each job asserts a documented threshold; a material regression fails the
benchmark suite. Thresholds are deliberately generous for CI machines; they
guard against order-of-magnitude regressions, not micro-differences. Every job
records a privacy-safe ``benchmark`` diagnostics event as a side effect.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from app.bench.runner import run_benchmark
from app.ingest.coordinator import ingest_v2, resolve_worker_count
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository

pytestmark = pytest.mark.benchmark

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"

# Documented thresholds (ms). Update only with a committed rationale.
THRESHOLDS = {
    "registry_microquery": 500.0,
    "deterministic_chat": 500.0,
    "cache_hit_chat": 200.0,
    "provider_timeout_chat": 500.0,
    "ingest_one_worker": 30_000.0,
    "ingest_auto_workers": 30_000.0,
    "ingest_explicit_workers": 30_000.0,
}


@pytest.fixture
def seeded_db() -> duckdb.DuckDBPyConnection:
    """One in-memory health DB seeded from the synthetic export fixture."""
    conn = duckdb.connect(":memory:")
    ingest_v2(xml_path=FIXTURE, db=conn, n_workers=1)
    return conn


@pytest.fixture
def isolated_state(tmp_path, monkeypatch) -> DiagnosticsRepository:
    """Isolate recorded benchmark events to a throwaway app-state store."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "bench.sqlite"))
    repo = DiagnosticsRepository()
    repo.clear()
    return repo


def _stub_client() -> object:
    """A client that is never awaited: the deterministic path stays local."""
    from unittest.mock import MagicMock

    return MagicMock()


def test_registry_microquery_benchmark(seeded_db) -> None:
    """A registry-owned trend query over the synthetic dataset is fast."""

    def run() -> object:
        from app.analytics.registry import execute_metric_trend

        return execute_metric_trend(
            seeded_db,
            {
                "metric_id": "steps",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "granularity": "week",
            },
        )

    result, duration_ms = run_benchmark(
        "registry_microquery", THRESHOLDS["registry_microquery"], run
    )
    assert result is not None
    assert duration_ms <= THRESHOLDS["registry_microquery"]


def test_deterministic_chat_benchmark(seeded_db, isolated_state) -> None:
    """A recognised question resolves locally without touching a provider."""
    import asyncio

    def run() -> str:
        orchestrator = ChatOrchestrator(client=_stub_client(), conn=seeded_db)
        return asyncio.run(orchestrator.answer("show my last run")).metadata.provenance

    result, duration_ms = run_benchmark("deterministic_chat", THRESHOLDS["deterministic_chat"], run)
    assert result == "deterministic_local"
    assert duration_ms <= THRESHOLDS["deterministic_chat"]


def test_cache_hit_chat_benchmark(seeded_db, isolated_state) -> None:
    """An exact cached answer is served without any provider or query work."""
    repository = AppStateRepository()
    repository.put_cached_response(
        "benchmark-key",
        "ds_benchmark",
        json.dumps({"template_id": "workout_card", "data": {}, "narrative": "cached"}),
    )

    def run() -> str | None:
        return repository.get_cached_response("benchmark-key", "ds_benchmark")

    result, duration_ms = run_benchmark("cache_hit_chat", THRESHOLDS["cache_hit_chat"], run)
    assert result is not None
    assert duration_ms <= THRESHOLDS["cache_hit_chat"]


def test_provider_timeout_chat_benchmark(seeded_db, isolated_state) -> None:
    """An unresolved question degrades to a local fallback when the provider is gone."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("provider unreachable"))

    def run() -> str:
        orchestrator = ChatOrchestrator(client=client, conn=seeded_db)
        response = asyncio.run(orchestrator.answer("tell me a story about my health"))
        return response.template_id

    result, duration_ms = run_benchmark(
        "provider_timeout_chat", THRESHOLDS["provider_timeout_chat"], run
    )
    assert result == "fallback"
    assert duration_ms <= THRESHOLDS["provider_timeout_chat"]


@pytest.mark.parametrize(
    ("mode", "workers"),
    [
        ("ingest_one_worker", 1),
        ("ingest_auto_workers", None),
        ("ingest_explicit_workers", 4),
    ],
)
def test_ingest_worker_benchmarks(mode: str, workers: int | None, tmp_path) -> None:
    """Ingest completes under threshold in one/auto/explicit worker modes."""

    source_size = FIXTURE.stat().st_size
    resolved = resolve_worker_count(source_size, cpu_count=8) if workers is None else workers

    def run() -> int:
        conn = duckdb.connect(":memory:")
        try:
            stats = ingest_v2(xml_path=FIXTURE, db=conn, n_workers=resolved)
        finally:
            conn.close()
        return int(stats["records"])

    result, duration_ms = run_benchmark(mode, THRESHOLDS[mode], run)
    assert result > 0
    assert duration_ms <= THRESHOLDS[mode]


def test_benchmark_events_are_recorded_and_clearable(isolated_state) -> None:
    """Benchmark runs leave clearable, privacy-safe diagnostics events."""
    run_benchmark("probe", 1000.0, lambda: None)
    events = isolated_state.recent(category="benchmark")
    assert any(event.name == "benchmark:probe" for event in events)
    isolated_state.clear()
    assert isolated_state.count() == 0


def test_local_planner_deterministic_benchmark(seeded_db) -> None:
    """Local question planning is deterministic and bounded."""
    from app.db.data_profile import get_data_profile

    profile = get_data_profile(seeded_db)

    def run() -> object:
        return plan_local_question("show my last run", profile)

    plan, duration_ms = run_benchmark("local_planner", 100.0, run, baseline_ms=5.0)
    assert plan is not None
    assert duration_ms <= 100.0
