"""Unit tests for scoped lifecycle operations on the local app-state store."""

from __future__ import annotations

import json

from app.state.app_state import AppStateRepository


def _repo(tmp_path) -> AppStateRepository:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()
    return repo


def test_cache_usage_and_clear_are_independent(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.put_cached_response("a", "ds", json.dumps({"x": 1}))
    repo.put_cached_response("b", "ds", json.dumps({"y": 2}))
    usage = repo.cache_usage()
    assert usage["entries"] == 2
    assert usage["bytes"] > 0
    assert repo.clear_cache() == 2
    assert repo.cache_usage() == {"entries": 0, "bytes": 0}


def test_delete_all_conversations_leaves_other_state(tmp_path) -> None:
    repo = _repo(tmp_path)
    first = repo.create_conversation("Runs", "ds")
    repo.add_completed_turn(first, "Show run", '{"template_id":"workout_card"}', "default", "local")
    repo.create_conversation("Sleep", None)
    repo.put_cached_response("k", "ds", json.dumps({"c": 1}))
    repo.create_saved_view("June", {"start": "2026-06-01"})

    assert repo.count_conversations() == 2
    assert repo.delete_all_conversations() == 2
    assert repo.count_conversations() == 0
    assert repo.get_turns(first) == []
    # Cache and saved views survive history deletion.
    assert repo.cache_usage()["entries"] == 1
    assert len(repo.list_saved_views()) == 1


def test_deactivate_active_dataset(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.activate(
        source_bytes=b"",
        source_size_bytes=0,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-01-01",
        coverage_end="2026-01-31",
        counts={"records": 1},
    )
    assert repo.get_active() is not None
    assert repo.deactivate_active_dataset() is True
    assert repo.get_active() is None
    # Idempotent: no active dataset means nothing to clear.
    assert repo.deactivate_active_dataset() is False
