"""Exact local cache never crosses dataset identities."""

from __future__ import annotations

from app.state.app_state import AppStateRepository


def test_exact_cache_is_scoped_to_dataset_and_refreshable(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("normalised-question", "ds_one", '{"answer":"one"}')
    assert repo.get_cached_response("normalised-question", "ds_one") == '{"answer":"one"}'
    assert repo.get_cached_response("normalised-question", "ds_two") is None
