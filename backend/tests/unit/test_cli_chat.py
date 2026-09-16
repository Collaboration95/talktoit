"""Unit tests for the headless chat CLI."""

from __future__ import annotations

import json
from datetime import date

import duckdb

from app.cli import chat as chat_cli
from app.db.data_profile import DataProfile
from app.llm.cache_keys import build_cache_key
from app.models.chat import ChatResponse, ResponseMetadata
from app.state.app_state import AppStateRepository


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


def test_ensure_local_server_ignores_non_local_provider(monkeypatch, capsys) -> None:
    """Groq mode never touches the LiteRT lifecycle or stderr."""
    from app.llm import litert

    def forbidden(*_args, **_kwargs):
        raise AssertionError("must not touch LiteRT for groq")

    monkeypatch.setattr(litert, "status", forbidden)
    chat_cli._ensure_local_server({"provider": "groq"})
    assert capsys.readouterr().err == ""


def test_ensure_local_server_noop_when_selected_endpoint_is_ready(monkeypatch, capsys) -> None:
    """A ready selected endpoint means silence — no spawn, no hint."""
    from app.llm import litert

    def forbidden(**_kwargs):
        raise AssertionError("must not spawn when already running")

    monkeypatch.setattr(litert, "health", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(litert, "ensure_running", forbidden)
    chat_cli._ensure_local_server({"provider": "local"})
    assert capsys.readouterr().err == ""


def test_ensure_local_server_hints_when_binary_missing(monkeypatch, capsys) -> None:
    """No binary is a stderr hint, never an exception."""
    from app.llm import litert

    monkeypatch.setattr(litert, "health", lambda **_kwargs: {"ok": False})
    monkeypatch.setattr(
        litert,
        "ensure_running",
        lambda **_kwargs: {"started": False, "running": False, "binary_available": False},
    )
    chat_cli._ensure_local_server({"provider": "local"})
    err = capsys.readouterr().err
    assert "litert-lm is not installed" in err
    assert "Settings" in err


def _activate_dataset(repo: AppStateRepository) -> str:
    """Create a minimal active dataset for CLI cache lifecycle tests."""
    dataset = repo.activate(
        source_bytes=b"",
        source_size_bytes=1,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-06-01",
        coverage_end="2026-06-30",
        counts={"records": 1},
        content_hash_prefix="cli-cache",
    )
    assert dataset is not None
    return dataset.id


def _fallback_response(question: str) -> ChatResponse:
    """Build a valid degraded response that must not enter the answer cache."""
    return ChatResponse(
        template_id="fallback",
        data={"question": question, "table": None, "text": "Provider unavailable."},
        narrative="Provider unavailable.",
        metadata=ResponseMetadata(provenance="fallback"),
    )


def test_cli_does_not_serve_or_write_degraded_cache_entries(tmp_path, monkeypatch) -> None:
    """A recovered CLI provider must not replay or persist a fallback response."""
    import asyncio

    repo = AppStateRepository(tmp_path / "state.sqlite")
    dataset_id = _activate_dataset(repo)
    question = "Show my last run"
    key = build_cache_key("exact", question)
    repo.put_cached_response(key, dataset_id, _fallback_response(question).model_dump_json())
    calls: list[str] = []

    class _Gateway:
        client = object()
        model = "test"

    class _Orchestrator:
        def __init__(self, **_kwargs) -> None:
            pass

        async def answer(self, received_question: str, plan_override=None) -> ChatResponse:
            assert plan_override is None
            calls.append(received_question)
            return _fallback_response(received_question)

    monkeypatch.setattr(chat_cli, "migrate", lambda _db_path=None: False)
    monkeypatch.setattr(chat_cli, "connect", lambda *_args, **_kwargs: duckdb.connect(":memory:"))
    monkeypatch.setattr(chat_cli, "AppStateRepository", lambda: repo)
    monkeypatch.setattr(chat_cli, "get_gateway_for_config", lambda _config: _Gateway())
    monkeypatch.setattr(chat_cli, "ChatOrchestrator", _Orchestrator)
    monkeypatch.setattr(chat_cli, "_ensure_local_server", lambda _config: None)
    monkeypatch.setattr(
        chat_cli,
        "get_data_profile",
        lambda _conn: DataProfile(
            first_date=date(2026, 6, 1),
            latest_date=date(2026, 6, 30),
            workout_types=("Running",),
            metrics=(),
        ),
    )

    response = asyncio.run(chat_cli._ask_question(question))

    assert calls == [question]
    assert response.metadata.provenance == "fallback"
    stored = repo.get_cached_entry(key, dataset_id)
    assert stored is not None
    assert stored[0] == _fallback_response(question).model_dump_json()

    uncached_question = "What did I eat?"
    asyncio.run(chat_cli._ask_question(uncached_question))

    assert calls == [question, uncached_question]
    assert repo.get_cached_entry(build_cache_key("exact", uncached_question), dataset_id) is None


def test_cli_leaves_shared_gateway_open(tmp_path, monkeypatch) -> None:
    """A CLI request borrows the process-cached gateway instead of closing it."""
    import asyncio

    repo = AppStateRepository(tmp_path / "state.sqlite")
    _activate_dataset(repo)

    class _Gateway:
        client = object()
        model = "test"

        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    gateway = _Gateway()

    class _Orchestrator:
        def __init__(self, **_kwargs) -> None:
            pass

        async def answer(self, question: str, plan_override=None) -> ChatResponse:
            assert plan_override is None
            return _fallback_response(question)

    monkeypatch.setattr(chat_cli, "migrate", lambda _db_path=None: False)
    monkeypatch.setattr(chat_cli, "connect", lambda *_args, **_kwargs: duckdb.connect(":memory:"))
    monkeypatch.setattr(chat_cli, "AppStateRepository", lambda: repo)
    monkeypatch.setattr(chat_cli, "get_gateway_for_config", lambda _config: gateway)
    monkeypatch.setattr(chat_cli, "ChatOrchestrator", _Orchestrator)
    monkeypatch.setattr(chat_cli, "_ensure_local_server", lambda _config: None)
    monkeypatch.setattr(
        chat_cli,
        "get_data_profile",
        lambda _conn: DataProfile(None, None, (), ()),
    )

    asyncio.run(chat_cli._ask_question("What did I eat?"))

    assert gateway.closed is False
