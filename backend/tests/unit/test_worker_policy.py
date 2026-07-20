"""Worker policy is deterministic and does not depend on export contents."""

from __future__ import annotations

from app.ingest.coordinator import resolve_worker_count


def test_small_exports_use_one_worker_even_on_large_cpu() -> None:
    assert resolve_worker_count(1_000_000, cpu_count=16) == 1


def test_auto_workers_reserve_capacity_and_cap_at_eight(monkeypatch) -> None:
    monkeypatch.setenv("TTI_INGEST_WORKERS", "auto")
    assert resolve_worker_count(32 * 1024 * 1024, cpu_count=4) == 3
    assert resolve_worker_count(32 * 1024 * 1024, cpu_count=99) == 8


def test_explicit_worker_override_wins_and_is_bounded() -> None:
    assert resolve_worker_count(1, requested=4, cpu_count=1) == 4
    assert resolve_worker_count(1, requested=99, cpu_count=1) == 8
