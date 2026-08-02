"""Unit tests for the headless chat CLI."""

from __future__ import annotations

import json

from app.cli import chat as chat_cli
from app.models.chat import ChatResponse


def test_cli_prints_json_output(monkeypatch, capsys) -> None:
    """The CLI should emit a machine-readable envelope when requested."""

    async def _fake_ask_question(
        question: str, db_path=None, conversation_id=None, parent_turn_id=None, cache_mode="default"
    ) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
        assert conversation_id is None
        assert parent_turn_id is None
        assert cache_mode == "default"
        return ChatResponse(
            template_id="fallback",
            data={
                "question": question,
                "table": None,
                "text": "No answer available.",
            },
            narrative="Try another question.",
        )

    monkeypatch.setattr(chat_cli, "_ask_question", _fake_ask_question)

    exit_code = chat_cli.main(["--question", "Show my last run", "--json"])

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["template_id"] == "fallback"
    assert body["data"]["question"] == "Show my last run"
    assert body["narrative"] == "Try another question."


def test_cli_prints_human_readable_output(monkeypatch, capsys) -> None:
    """The default CLI output should stay readable for interactive use."""

    async def _fake_ask_question(
        question: str, db_path=None, conversation_id=None, parent_turn_id=None, cache_mode="default"
    ) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
        assert conversation_id is None
        assert parent_turn_id is None
        assert cache_mode == "default"
        return ChatResponse(
            template_id="workout_card",
            data={
                "activity_type": "Running",
                "date": "2026-06-05T07:00:00+08:00",
                "duration_minutes": 45.5,
                "avg_heart_rate": 148,
                "max_heart_rate": 178,
                "distance_meters": 8500.0,
                "distance_unit": "km",
                "energy_burned_kj": 2500.0,
                "elevation_ascent_meters": 45.0,
            },
            narrative="You ran 45.5 minutes on June 5.",
        )

    monkeypatch.setattr(chat_cli, "_ask_question", _fake_ask_question)

    exit_code = chat_cli.main(["--question", "Show my last run"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Template: workout_card" in output
    assert "You ran 45.5 minutes on June 5." in output


def test_cli_passes_local_conversation_id_to_headless_lifecycle(monkeypatch, capsys) -> None:
    """The headless path can append a durable local conversation turn."""

    async def _fake_ask_question(
        question: str, db_path=None, conversation_id=None, parent_turn_id=None, cache_mode="default"
    ) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
        assert conversation_id == "cv_local"
        assert parent_turn_id is None
        assert cache_mode == "default"
        return ChatResponse(
            template_id="fallback",
            data={"question": question, "table": None, "text": "No answer available."},
            narrative="Try another question.",
        )

    monkeypatch.setattr(chat_cli, "_ask_question", _fake_ask_question)
    assert chat_cli.main(["--question", "Show my last run", "--conversation-id", "cv_local"]) == 0
    assert "Narrative: Try another question." in capsys.readouterr().out


def test_cli_passes_fresh_cache_mode(monkeypatch) -> None:
    """The CLI exposes the same cache refresh contract as HTTP chat."""

    async def _fake_ask_question(
        question: str, db_path=None, conversation_id=None, parent_turn_id=None, cache_mode="default"
    ) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
        assert conversation_id is None
        assert parent_turn_id is None
        assert cache_mode == "fresh"
        return ChatResponse(
            template_id="fallback",
            data={"question": question, "table": None, "text": "No answer available."},
            narrative="Try another question.",
        )

    monkeypatch.setattr(chat_cli, "_ask_question", _fake_ask_question)
    assert chat_cli.main(["--question", "Show my last run", "--cache-mode", "fresh"]) == 0


def test_cli_passes_scoped_parent_turn_id(monkeypatch) -> None:
    """The headless client can request deterministic follow-up resolution."""

    async def _fake_ask_question(
        question: str, db_path=None, conversation_id=None, parent_turn_id=None, cache_mode="default"
    ) -> ChatResponse:
        assert question == "Compare that to prior period"
        assert db_path is None
        assert conversation_id == "cv_local"
        assert parent_turn_id == "tr_parent"
        assert cache_mode == "default"
        return ChatResponse(
            template_id="fallback",
            data={"question": question, "table": None, "text": "No answer available."},
            narrative="Try another question.",
        )

    monkeypatch.setattr(chat_cli, "_ask_question", _fake_ask_question)
    assert (
        chat_cli.main(
            [
                "--question",
                "Compare that to prior period",
                "--conversation-id",
                "cv_local",
                "--parent-turn-id",
                "tr_parent",
            ]
        )
        == 0
    )


def test_cli_migrates_database_before_read_only_open(monkeypatch) -> None:
    """Headless chat repairs a stale schema before opening its read-only DB."""
    import asyncio

    import pytest

    events: list[str] = []

    def _fake_migrate(db_path=None) -> bool:
        assert db_path is None
        events.append("migrate")
        return False

    def _fake_connect(db_path=None, *, read_only=False):
        events.append(f"connect:{read_only}")
        raise RuntimeError("intentional stop after migration")

    monkeypatch.setattr(chat_cli, "migrate", _fake_migrate)
    monkeypatch.setattr(chat_cli, "connect", _fake_connect)

    with pytest.raises(RuntimeError, match="intentional stop"):
        asyncio.run(chat_cli._ask_question("Show my last run"))

    assert events == ["migrate", "connect:True"]
