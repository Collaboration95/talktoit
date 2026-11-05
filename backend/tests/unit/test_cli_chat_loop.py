"""Input, streaming and safe-output contracts for headless chat."""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from app.cli import chat
from app.db.dataset_lifecycle import DatasetBusyError, DatasetRecoveryError
from app.models.chat import ChatResponse


def _response(question):
    return ChatResponse(
        template_id="fallback",
        data={"question": question, "text": "Safe guidance.", "table": None},
        narrative="Safe guidance.",
    )


def test_loop_emits_ndjson_with_one_event_loop_and_session(monkeypatch, capsys):
    calls = []

    async def ask(question, **options):
        calls.append((question, asyncio.get_running_loop(), options))
        return _response(question)

    monkeypatch.setattr(chat, "_ask_question", ask)
    monkeypatch.setattr(
        chat.sys, "stdin", io.StringIO("\nFirst question\nSecond question\n/quit\n")
    )
    assert chat.main(["--interactive", "--json", "--local-model", "installed-model"]) == 0
    captured = capsys.readouterr()
    envelopes = [json.loads(line) for line in captured.out.splitlines()]
    assert [body["data"]["question"] for body in envelopes] == ["First question", "Second question"]
    assert captured.err == ""
    assert calls[0][1] is calls[1][1]
    assert calls[0][2]["session"] is calls[1][2]["session"]
    assert calls[0][2]["local_model"] == "installed-model"


def test_interactive_json_prompts_are_only_on_stderr(monkeypatch, capsys):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    async def ask(question, **_options):
        return _response(question)

    monkeypatch.setattr(chat, "_ask_question", ask)
    monkeypatch.setattr(chat.sys, "stdin", Terminal("One question\n/exit\n"))
    assert chat.main(["--interactive", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["narrative"] == "Safe guidance."
    assert "You: " in captured.err
    assert "/quit" in captured.err


def test_loop_accepts_initial_question_then_stdin(monkeypatch, capsys):
    questions = []

    async def ask(question, **_options):
        questions.append(question)
        return _response(question)

    monkeypatch.setattr(chat, "_ask_question", ask)
    monkeypatch.setattr(chat.sys, "stdin", io.StringIO("Next question\n"))
    assert chat.main(["--interactive", "--question", "Initial question"]) == 0
    assert questions == ["Initial question", "Next question"]
    assert "You: Initial question" in capsys.readouterr().out


@pytest.mark.parametrize("stdin", ["", "  \n"])
def test_empty_one_shot_stdin_is_an_input_error(monkeypatch, capsys, stdin):
    monkeypatch.setattr(chat.sys, "stdin", io.StringIO(stdin))
    assert chat.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1 and 2,000" in captured.err


@pytest.mark.parametrize("question", [" ", "x" * 2001])
def test_invalid_explicit_question_does_not_fall_back_to_stdin(monkeypatch, capsys, question):
    monkeypatch.setattr(chat.sys, "stdin", io.StringIO("must not be read"))
    assert chat.main(["--question", question]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    if question.strip():
        assert question not in captured.err
    assert "must not be read" not in captured.err


def test_loop_recovers_from_oversized_input(monkeypatch, capsys):
    questions = []

    async def ask(question, **_options):
        questions.append(question)
        return _response(question)

    monkeypatch.setattr(chat, "_ask_question", ask)
    monkeypatch.setattr(chat.sys, "stdin", io.StringIO("x" * 2001 + "\nValid question\n"))
    assert chat.main(["--interactive", "--json"]) == 0
    captured = capsys.readouterr()
    assert questions == ["Valid question"]
    assert json.loads(captured.out)["data"]["question"] == "Valid question"
    assert "1 and 2,000" in captured.err


@pytest.mark.parametrize(
    "error,exit_code,hint",
    [
        (DatasetBusyError(), 1, "busy"),
        (DatasetRecoveryError(), 1, "safely"),
        (OSError("SELECT private_path"), 1, "local setup"),
        (ValueError("SELECT private_path"), 1, "local setup"),
        (KeyboardInterrupt(), 130, "interrupted"),
    ],
)
def test_failures_have_safe_stderr_and_exit_codes(monkeypatch, capsys, error, exit_code, hint):
    async def ask(*_args, **_options):
        raise error

    monkeypatch.setattr(chat, "_ask_question", ask)
    assert chat.main(["--question", "A complete question", "--json"]) == exit_code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert hint in captured.err
    assert "SELECT" not in captured.err
    assert "private_path" not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("args", [["--parent-turn-id", "turn"], ["--local-model", "  "]])
def test_invalid_options_exit_before_startup(capsys, args):
    with pytest.raises(SystemExit) as exc:
        chat.main(args)
    assert exc.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_human_fallback_does_not_dump_payload_or_internal_fields(capsys):
    response = _response("A question")
    response.data["table"] = [{"key": "debug", "value": "SELECT secret FROM private_path"}]
    chat._print_response(response, False, "A question")
    captured = capsys.readouterr()
    assert captured.out == "You: A question\nSafe guidance.\n"


def test_empty_narrative_has_useful_human_fallback(capsys):
    response = _response("A question")
    response.narrative = " "
    chat._print_response(response, False, "A question")
    assert "Try a complete question" in capsys.readouterr().out


def test_one_shot_pipe_keeps_multiline_question_and_pretty_json(monkeypatch, capsys):
    async def ask(question, **options):
        assert question == "First line\nsecond line"
        assert options["session"] is None
        return _response(question)

    monkeypatch.setattr(chat, "_ask_question", ask)
    monkeypatch.setattr(chat.sys, "stdin", io.StringIO("First line\nsecond line\n"))
    assert chat.main(["--json"]) == 0
    captured = capsys.readouterr()
    assert '\n  "template_id"' in captured.out
    assert json.loads(captured.out)["data"]["question"] == "First line\nsecond line"
