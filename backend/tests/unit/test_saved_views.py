"""Saved dashboard scopes persist independently of rebuildable health data."""

from __future__ import annotations

from app.state.app_state import AppStateRepository


def test_saved_view_round_trips_scope_without_source_path(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    view_id = repo.create_saved_view("January runs", {"start": "2024-01-01", "end": "2024-01-31"})
    saved = repo.list_saved_views()
    assert saved[0]["id"] == view_id
    assert saved[0]["query"] == {"end": "2024-01-31", "start": "2024-01-01"}
    assert "source_path" not in saved[0]
