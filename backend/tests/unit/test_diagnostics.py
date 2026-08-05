"""Unit tests for the local diagnostics store and its privacy boundary."""

from __future__ import annotations

import json

import pytest

from app.state.diagnostics import (
    FORBIDDEN_CONTENT_TOKENS,
    FORBIDDEN_META_KEYS,
    DiagnosticsRepository,
    safe_record,
    timed_record,
)


def _repo(tmp_path) -> DiagnosticsRepository:
    repo = DiagnosticsRepository(tmp_path / "diag.sqlite")
    repo.clear()
    return repo


# ---------------------------------------------------------------------------
# Recording, listing, and clearing
# ---------------------------------------------------------------------------


def test_record_recent_and_clear(tmp_path) -> None:
    repo = _repo(tmp_path)
    event_id = repo.record(
        "panel",
        "panel:summary",
        duration_ms=12.5,
        status="success",
        meta={"panel_name": "summary", "state": "success"},
        counts={"rows": 7},
    )
    assert event_id.startswith("de_")

    events = repo.recent()
    assert len(events) == 1
    event = events[0]
    assert event.category == "panel"
    assert event.name == "panel:summary"
    assert event.duration_ms == pytest.approx(12.5)
    assert event.meta == {"panel_name": "summary", "state": "success"}
    assert event.counts == {"rows": 7}

    assert repo.count() == 1
    assert repo.clear() == 1
    assert repo.count() == 0


def test_recent_filters_by_category_and_orders_newest_first(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.record("query", "get_trend", meta={"query_name": "get_trend", "state": "ok"})
    repo.record("chat", "chat_request", meta={"plan_mode": "local", "cache_outcome": "local"})
    repo.record("query", "get_comparison", meta={"query_name": "get_comparison", "state": "ok"})

    only_query = repo.recent(category="query")
    assert [event.name for event in only_query] == ["get_comparison", "get_trend"]

    limited = repo.recent(limit=1)
    assert len(limited) == 1
    assert limited[0].name == "get_comparison"


def test_count_by_category(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.record("app", "startup", meta={"app_version": "0.1.0"})
    repo.record("app", "startup", meta={"app_version": "0.1.0"})
    repo.record("panel", "panel:steps", meta={"panel_name": "steps", "state": "empty"})
    assert repo.count("app") == 2
    assert repo.count("panel") == 1
    assert repo.count() == 3
    assert repo.clear() == 3


# ---------------------------------------------------------------------------
# Privacy boundary: metadata is allowlisted per category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category",
    ["import", "query", "chat", "planner", "narrator", "panel", "app", "benchmark"],
)
def test_allowed_meta_keys_are_accepted(category: str) -> None:
    allowed_by_category = {
        "import": {"parser_mode": "v2", "worker_count": "4", "schema_version": "1"},
        "query": {"query_name": "get_trend", "state": "ok", "cache_outcome": "uncached"},
        "chat": {"plan_mode": "local", "cache_outcome": "deterministic_local"},
        "planner": {"mode": "local", "model": "local", "error_class": ""},
        "narrator": {"mode": "local", "model": "local", "error_class": ""},
        "panel": {"panel_name": "steps", "state": "success"},
        "app": {"app_version": "0.1.0", "duckdb_version": "1.2", "schema_version": "1"},
        "benchmark": {"benchmark_name": "query", "baseline_ms": "5", "threshold_ms": "20"},
    }
    from app.state.diagnostics import _validate_event

    _validate_event(category, "name", "ok", allowed_by_category[category])


def test_forbidden_meta_keys_are_rejected(tmp_path) -> None:
    repo = _repo(tmp_path)
    for key in list(FORBIDDEN_META_KEYS):
        with pytest.raises(ValueError):
            repo.record(
                "chat",
                "chat_request",
                meta={key: "anything"},  # must be rejected before it is stored
            )


def test_unknown_category_and_bad_fields_are_rejected(tmp_path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        repo.record("unknown_category", "x")
    with pytest.raises(ValueError):
        repo.record("chat", "")
    with pytest.raises(ValueError):
        repo.record("chat", "x" * 121)
    with pytest.raises(ValueError):
        repo.record("chat", "x", status="")
    with pytest.raises(ValueError):
        repo.record("chat", "x", meta={"question": "hi"})


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregate_reports_latency_and_cache_rate(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.record(
        "chat",
        "run",
        duration_ms=100,
        meta={"plan_mode": "cached", "cache_outcome": "cached"},
        counts={"cache_hits": 1, "cache_misses": 0},
    )
    for _ in range(3):
        repo.record(
            "chat",
            "run",
            duration_ms=200,
            meta={"plan_mode": "local", "cache_outcome": "deterministic_local"},
            counts={"cache_hits": 0, "cache_misses": 1},
        )
    repo.record(
        "panel",
        "steps",
        status="empty",
        duration_ms=50,
        meta={"panel_name": "steps", "state": "empty"},
    )

    agg = repo.aggregate()
    assert agg["total_events"] == 5
    assert agg["cache"] == {"hits": 1, "misses": 3, "hit_rate": 0.25}
    assert agg["cache_outcomes"] == {"cached": 1, "deterministic_local": 3}
    chat_bucket = agg["by_category"]["chat"]
    assert chat_bucket["count"] == 4
    assert chat_bucket["mean_duration_ms"] == pytest.approx(175.0)
    assert chat_bucket["p95_duration_ms"] == pytest.approx(200.0)
    assert agg["status_counts"] == {"ok": 4, "empty": 1}


def test_aggregate_empty_has_no_missing_keys(tmp_path) -> None:
    agg = _repo(tmp_path).aggregate()
    assert agg["total_events"] == 0
    assert agg["cache"]["hit_rate"] is None
    assert agg["by_category"] == {}


# ---------------------------------------------------------------------------
# Privacy audit of the on-disk representation
# ---------------------------------------------------------------------------


def test_stored_event_json_contains_no_forbidden_content(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.record(
        "import",
        "ingest",
        duration_ms=1500,
        status="ok",
        meta={"parser_mode": "v2", "schema_version": "1", "worker_count": "8"},
        counts={"records": 1000, "workouts": 4},
    )
    repo.record(
        "query",
        "get_trend",
        duration_ms=3,
        meta={"query_name": "get_trend", "state": "success", "cache_outcome": "uncached"},
    )
    stored = json.dumps([event.public_dict() for event in repo.recent()])
    lowered = stored.casefold()
    for token in FORBIDDEN_CONTENT_TOKENS:
        assert token.casefold() not in lowered, f"leaked content token: {token}"


def test_safe_and_timed_record_never_raise(tmp_path) -> None:
    import time

    repo = _repo(tmp_path)
    safe_record(repo, "chat", "run")  # normal
    timed_record(repo, "panel", "list", time.perf_counter())
    # A bad call must be swallowed, not raised, on the live product path.
    safe_record(repo, "chat", "run", meta={"question": "hi"})
    safe_record(None, "chat", "run")  # default path must not raise
    assert repo.count() == 2
