"""Unit tests for the headless chat CLI."""

from __future__ import annotations

import json

from app.cli import chat as chat_cli
from app.models.chat import ChatResponse


def test_cli_prints_json_output(monkeypatch, capsys) -> None:
    """The CLI should emit a machine-readable envelope when requested."""

    async def _fake_ask_question(question: str, db_path=None) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
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

    async def _fake_ask_question(question: str, db_path=None) -> ChatResponse:
        assert question == "Show my last run"
        assert db_path is None
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
