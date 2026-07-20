"""Durable local transcript contracts."""

from __future__ import annotations

from app.state.app_state import AppStateRepository


def test_conversation_turns_survive_repository_reopen_in_order(tmp_path) -> None:
    path = tmp_path / "state.sqlite"
    repo = AppStateRepository(path)
    conversation_id = repo.create_conversation("Runs", "ds_fixture")
    repo.add_completed_turn(
        conversation_id,
        "first",
        '{"template_id":"fallback"}',
        "default",
        "deterministic_local",
        {"tool_name": "get_last_workout"},
    )
    repo.add_completed_turn(
        conversation_id, "second", '{"template_id":"fallback"}', "fresh", "fallback"
    )

    restored = AppStateRepository(path)
    assert [turn["question"] for turn in restored.get_turns(conversation_id)] == ["first", "second"]
    assert (
        restored.get_turns(conversation_id)[0]["canonical_plan_json"]
        == '{"tool_name": "get_last_workout"}'
    )
    assert restored.list_conversations()[0]["id"] == conversation_id


def test_rename_and_delete_touch_only_selected_conversation(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite")
    selected = repo.create_conversation("Before", "ds_fixture")
    other = repo.create_conversation("Other", "ds_fixture")
    repo.add_completed_turn(selected, "question", "{}", "default", "fallback")

    assert repo.rename_conversation(selected, "After")
    assert repo.delete_conversation(selected)
    assert repo.get_turns(selected) == []
    assert repo.list_conversations()[0]["id"] == other


def test_archive_hides_only_selected_conversation_and_preserves_turns(tmp_path) -> None:
    repo = AppStateRepository(tmp_path / "state.sqlite3")
    archived = repo.create_conversation("Archive me", "ds_fixture")
    visible = repo.create_conversation("Keep me", "ds_fixture")
    repo.add_completed_turn(archived, "question", "{}", "default", "fallback")

    assert repo.archive_conversation(archived)
    assert [conversation["id"] for conversation in repo.list_conversations()] == [visible]
    assert len(repo.get_turns(archived)) == 1
