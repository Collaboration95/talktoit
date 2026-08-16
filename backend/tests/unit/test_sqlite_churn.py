"""GH-3 — per-request SQLite churn is bounded.

The app-state repositories run migrations once per repository instance, the
chat path shares one session connection across a batch of accessors, and
diagnostics stage into a request-scoped buffer flushed over one connection.
These tests count ``sqlite3.connect`` calls to prove the budget.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository


@pytest.fixture
def _count_connects(monkeypatch):
    """Count every SQLite connect across both repositories."""
    calls: dict[str, int] = {"n": 0}
    real_connect = sqlite3.connect

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr("app.state.app_state.sqlite3.connect", counting)
    monkeypatch.setattr("app.state.diagnostics.sqlite3.connect", counting)
    return calls


def test_migration_runs_once_per_repository_instance(tmp_path, _count_connects) -> None:
    """Accessors no longer open a migration connection on every call."""
    calls = _count_connects
    repo = AppStateRepository(tmp_path / "state.sqlite")

    repo.get_active()
    repo.get_active()
    repo.get_turns("nope")
    repo.cache_usage()

    # One migration connection + one connection per real accessor; a second
    # ``get_active`` never re-runs the schema chain.
    assert calls["n"] == 5


def test_session_batches_accessors_into_one_connection(tmp_path, _count_connects) -> None:
    """A session block runs many accessors over a single connection."""
    calls = _count_connects
    repo = AppStateRepository(tmp_path / "state.sqlite")

    with repo.session() as store:
        assert repo.get_active(conn=store) is None
        assert repo.get_conversation("nope", conn=store) is None
        assert repo.get_turns("nope", conn=store) == []

    # One migration connection + one shared session connection.
    assert calls["n"] == 2


def test_shared_connection_never_closes_the_callers_session(tmp_path, _count_connects) -> None:
    """Accessors using a caller-provided connection must not close it."""
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()

    conversation_id = repo.create_conversation("History", "ds_one")
    with repo.session() as store:
        repo.create_pending_turn(conversation_id, "question", "default", conn=store)
        # The connection must still be usable after each accessor returns.
        assert repo.get_turns(conversation_id, conn=store)[0]["state"] == "pending"


def test_diagnostics_buffer_flushes_all_events_in_one_connection(tmp_path, _count_connects) -> None:
    """A request's diagnostics flush once instead of once per event."""
    calls = _count_connects
    repo = DiagnosticsRepository(tmp_path / "diag.sqlite")

    with repo.buffer() as buffer:
        buffer.record("chat", "a", duration_ms=1.0, meta={"plan_mode": "local"})
        buffer.record("chat", "b", duration_ms=2.0, meta={"plan_mode": "cached"})
        buffer.record("panel", "c", meta={"panel_name": "steps", "state": "ok"})
    assert calls["n"] == 2  # migration + one flush

    assert repo.count() == 3
    assert repo.recent(category="chat")[0].name == "b"


def test_diagnostics_buffer_validates_up_front_and_never_breaks(tmp_path) -> None:
    """A forbidden metadata key fails fast even inside a request-scoped buffer."""
    repo = DiagnosticsRepository(tmp_path / "diag.sqlite")
    with repo.buffer() as buffer:
        with pytest.raises(ValueError):
            buffer.record("chat", "bad", meta={"question": "leak"})
        assert repo.count() == 0


def test_diagnostics_buffer_is_request_scoped(tmp_path) -> None:
    """Two concurrent buffers never share staged events."""
    repo = DiagnosticsRepository(tmp_path / "diag.sqlite")
    first = repo.buffer()
    second = repo.buffer()
    first.record("chat", "one", meta={"plan_mode": "local"})
    second.record("chat", "two", meta={"plan_mode": "cached"})
    first.flush()
    second.flush()
    names = {event.name for event in repo.recent(category="chat")}
    assert names == {"one", "two"}
