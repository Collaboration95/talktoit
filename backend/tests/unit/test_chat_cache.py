"""Exact local cache never crosses dataset identities."""

from __future__ import annotations

from app.state.app_state import CACHE_MAX_ENTRIES, AppStateRepository


def test_exact_cache_is_scoped_to_dataset_and_refreshable(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("normalised-question", "ds_one", '{"answer":"one"}')
    assert repo.get_cached_response("normalised-question", "ds_one") == '{"answer":"one"}'
    assert repo.get_cached_response("normalised-question", "ds_two") is None


def test_canonical_cache_key_can_share_equivalent_local_intent(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.put_cached_response("canonical-last-running", "ds_one", '{"template_id":"workout_card"}')
    assert (
        repo.get_cached_response("canonical-last-running", "ds_one")
        == '{"template_id":"workout_card"}'
    )


def test_lru_cache_eviction_is_bounded_and_does_not_touch_turns(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    conversation_id = repo.create_conversation("History", "ds_one")
    turn_id = repo.add_completed_turn(conversation_id, "source", "{}", "default", "fallback")
    for index in range(CACHE_MAX_ENTRIES + 1):
        repo.put_cached_response(f"key-{index}", "ds_one", "{}")
    assert repo.get_cached_response("key-0", "ds_one") is None
    assert repo.get_cached_response(f"key-{CACHE_MAX_ENTRIES}", "ds_one") == "{}"
    assert repo.get_turns(conversation_id)[0]["id"] == turn_id
