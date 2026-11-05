"""Real headless cache regressions using two synthetic health databases."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import _get_gateway
from app.cli import chat as chat_cli
from app.db.data_profile import get_data_profile
from app.db.dataset_lifecycle import DatasetLifecycle
from app.ingest.coordinator import ingest_v2
from app.llm import cache_keys
from app.llm.local_planner import plan_local_question
from app.llm.provider_gateway import ProviderUnavailableError
from app.main import create_app
from app.models.chat import ChatResponse
from app.state.app_state import AppStateRepository

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
QUESTION = "Show my last run"


@pytest.fixture
def databases(tmp_path, monkeypatch):
    managed = tmp_path / "a.duckdb"
    override = tmp_path / "b.duckdb"
    for path, duration in ((managed, 45.5), (override, 999)):
        with duckdb.connect(str(path)) as conn:
            ingest_v2(FIXTURE, conn, n_workers=1)
            conn.execute(
                "UPDATE workouts SET duration = ? WHERE activity_type = 'Running'", [duration]
            )
    monkeypatch.setenv("TTI_DB_PATH", str(managed))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    with duckdb.connect(str(managed), read_only=True) as conn:
        profile = get_data_profile(conn)
        counts = {
            name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]  # noqa: S608
            for name in (
                "records",
                "record_metadata",
                "hrv_beats",
                "workouts",
                "workout_events",
                "workout_statistics",
                "workout_routes",
                "workout_metadata",
                "activity_summaries",
            )
        }
    active = repo.build_file_manifest(
        FIXTURE,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start=profile.first_date.isoformat(),
        coverage_end=profile.latest_date.isoformat(),
        counts=counts,
    )
    lifecycle = DatasetLifecycle(managed)
    with lifecycle.writer_lock():
        staging = lifecycle.new_staging()
        shutil.copyfile(managed, staging)
        lifecycle.activate(staging, active, FIXTURE.parent, repo)
    gateway = Mock(client=object(), model="stub")
    gateway.complete = AsyncMock(side_effect=ProviderUnavailableError("Synthetic offline provider"))
    monkeypatch.setattr(chat_cli, "_ensure_local_server", Mock())
    monkeypatch.setattr(chat_cli, "get_gateway_for_config", lambda _config: gateway)
    return repo, managed, override, active, gateway


def _run(capsys, path=None, question=QUESTION, *options):
    args = ["--question", question, "--json", *options]
    if path is not None:
        args.extend(["--db-path", str(path)])
    assert chat_cli.main(args) == 0
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def _cache_snapshot(repo):
    with repo.session() as conn:
        return [
            tuple(row) for row in conn.execute("SELECT * FROM cache_entries ORDER BY cache_key")
        ]


@pytest.mark.parametrize("cache_mode", ["default", "fresh"])
@pytest.mark.parametrize("cache_kind", ["exact", "canonical", "empty"])
def test_unmatched_override_never_reads_writes_or_labels_with_a(
    databases, capsys, cache_kind, cache_mode
):
    repo, _managed, override, active, gateway = databases
    first, _ = _run(capsys)
    assert first["data"]["duration_minutes"] == 45.5
    assert first["metadata"]["dataset_version_id"] == active.id
    with repo.session() as conn:
        rows = conn.execute("SELECT cache_key, canonical_plan_json FROM cache_entries").fetchall()
        assert len(rows) == 2  # The real CLI populated both exact and canonical keys.
        if cache_kind == "canonical":
            from app.llm.cache_keys import build_cache_key, generation_identity

            exact = build_cache_key(
                "exact",
                QUESTION,
                generation_identity=generation_identity(repo.get_provider_config()),
            )
            conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", [exact])
        elif cache_kind == "empty":
            conn.execute("DELETE FROM cache_entries")
    before = _cache_snapshot(repo)
    response, _ = _run(capsys, override, QUESTION, "--cache-mode", cache_mode)
    assert response["data"]["duration_minutes"] == 999
    assert response["metadata"]["provenance"] == "deterministic_local"
    for key in ("dataset_version_id", "coverage_start", "coverage_end", "generated_at", "turn_id"):
        assert response["metadata"][key] is None
    assert _cache_snapshot(repo) == before  # Includes hit counts and access times.
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize("path_kind", ["default", "explicit", "relative", "normalized", "symlink"])
def test_equivalent_managed_paths_keep_shared_exact_and_canonical_cache(
    databases, capsys, monkeypatch, tmp_path, path_kind
):
    repo, managed, _override, active, gateway = databases
    first, _ = _run(capsys)
    if path_kind == "default":
        path = None
    elif path_kind == "relative":
        monkeypatch.chdir(tmp_path)
        path = Path(managed.name)
    elif path_kind == "normalized":
        (tmp_path / "folder").mkdir()
        path = tmp_path / "folder" / ".." / managed.name
    elif path_kind == "symlink":
        path = tmp_path / "alias.duckdb"
        path.symlink_to(managed)
    else:
        path = managed
    exact, _ = _run(capsys, path)
    assert exact["metadata"]["provenance"] == "cached"
    assert exact["data"] == first["data"]
    with repo.session() as conn:
        conn.execute("DELETE FROM cache_entries WHERE hit_count > 0")
    canonical, _ = _run(capsys, path)
    assert canonical["metadata"]["provenance"] == "cached"
    assert canonical["metadata"]["dataset_version_id"] == active.id
    fresh, _ = _run(capsys, path, QUESTION, "--cache-mode", "fresh")
    assert fresh["metadata"]["provenance"] == "deterministic_local"
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize("use_override", [False, True])
def test_no_active_manifest_bypasses_cache_and_conversation(databases, capsys, use_override):
    repo, _managed, override, active, gateway = databases
    _run(capsys)
    conversation = repo.create_conversation("A history", active.id)
    with repo.session() as conn:
        conn.execute("DELETE FROM app_state WHERE key = 'active_dataset_id'")
    if not use_override:
        # No authoritative pointer or manifest: model a pre-lifecycle,
        # unassociated DB. A committed pointer would correctly repair SQLite.
        shutil.rmtree(DatasetLifecycle().root)
    before = _cache_snapshot(repo)
    response, hint = _run(
        capsys, override if use_override else None, QUESTION, "--conversation-id", conversation
    )
    assert response["data"]["duration_minutes"] == (999 if use_override else 45.5)
    assert response["metadata"]["dataset_version_id"] is None
    assert response["metadata"]["turn_id"] is None
    assert repo.get_turns(conversation) == []
    assert "conversation" in hint.lower()
    assert _cache_snapshot(repo) == before
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize("followup", [False, True])
def test_unmatched_database_does_not_append_or_resolve_a_history(databases, capsys, followup):
    repo, _managed, override, active, gateway = databases
    conversation = repo.create_conversation("A history", active.id)
    parent, _ = _run(capsys, None, QUESTION, "--conversation-id", conversation)
    turns = repo.get_turns(conversation)
    before = _cache_snapshot(repo)
    options = ["--conversation-id", conversation]
    if followup:
        options += ["--parent-turn-id", parent["metadata"]["turn_id"]]
    response, hint = _run(capsys, override, QUESTION, *options)
    assert response["data"]["duration_minutes"] == 999
    assert response["metadata"]["turn_id"] is None
    assert response["metadata"]["dataset_version_id"] is None
    assert repo.get_turns(conversation) == turns
    assert _cache_snapshot(repo) == before
    assert "conversation" in hint.lower()
    assert str(override) not in hint
    gateway.complete.assert_not_awaited()


def test_contextual_followup_on_b_has_useful_fallback_without_a_context(databases, capsys):
    repo, _managed, override, active, _gateway = databases
    conversation = repo.create_conversation("A history", active.id)
    parent, _ = _run(capsys, None, QUESTION, "--conversation-id", conversation)
    turns = repo.get_turns(conversation)
    before = _cache_snapshot(repo)
    response, hint = _run(
        capsys,
        override,
        "Compare that to prior period",
        "--conversation-id",
        conversation,
        "--parent-turn-id",
        parent["metadata"]["turn_id"],
    )
    assert response["template_id"] == "fallback"
    assert response["narrative"]
    assert "complete question" in hint
    assert response["metadata"]["turn_id"] is None
    assert response["metadata"]["dataset_version_id"] is None
    assert repo.get_turns(conversation) == turns
    assert _cache_snapshot(repo) == before
    assert "SELECT" not in response["narrative"]
    assert str(override) not in hint + response["narrative"]


def test_unresolvable_paths_do_not_prove_shared_identity(tmp_path):
    from app.llm.cache_keys import matches_managed_database

    missing = tmp_path / "missing.duckdb"
    assert not matches_managed_database(missing, missing)
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    assert not matches_managed_database(loop, loop)


@pytest.mark.parametrize("kind", ["exact", "canonical"])
def test_pre_fix_mislabeled_cache_entries_are_invalidated(databases, capsys, monkeypatch, kind):
    from app.llm import cache_keys

    repo, _managed, override, active, gateway = databases
    poisoned, _ = _run(capsys, override)
    assert poisoned["data"]["duration_minutes"] == 999
    value = (
        QUESTION
        if kind == "exact"
        else {
            "tool_name": "get_last_workout",
            "arguments": {"activity_type": "Running"},
        }
    )
    with monkeypatch.context() as patch:
        patch.setattr(cache_keys, "CACHE_KEY_VERSION", "chat-cache-v3")
        old_key = cache_keys.build_cache_key(
            kind,
            value,
            generation_identity=cache_keys.generation_identity(repo.get_provider_config()),
        )
    repo.put_cached_response(old_key, active.id, json.dumps(poisoned))
    response, _ = _run(capsys)
    assert response["data"]["duration_minutes"] == 45.5
    assert response["metadata"]["provenance"] == "deterministic_local"
    with repo.session() as conn:
        assert (
            conn.execute(
                "SELECT hit_count FROM cache_entries WHERE cache_key = ?", [old_key]
            ).fetchone()[0]
            == 0
        )
    gateway.complete.assert_not_awaited()


def test_interactive_loop_persists_scoped_turns_and_resolves_followup(
    databases, monkeypatch, capsys
):
    repo, _managed, _override, active, gateway = databases
    monkeypatch.setattr(
        chat_cli.sys,
        "stdin",
        io.StringIO("Show running volume this week\nCompare that to prior period\n/quit\n"),
    )
    assert chat_cli.main(["--interactive", "--json", "--local"]) == 0
    responses = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["template_id"] for item in responses] == ["period_summary", "comparison"]
    assert all(item["metadata"]["dataset_version_id"] == active.id for item in responses)
    conversations = repo.list_conversations()
    assert len(conversations) == 1
    turns = repo.get_turns(str(conversations[0]["id"]))
    assert [turn["id"] for turn in turns] == [item["metadata"]["turn_id"] for item in responses]
    assert all(turn["state"] == "completed" for turn in turns)
    # A fixed fixture date anchors relative questions, regardless of today's date.
    assert responses[0]["data"]["period_end"] == active.coverage_end
    chat_cli._ensure_local_server.assert_not_called()
    gateway.complete.assert_not_awaited()


def test_external_interactive_loop_does_not_create_shared_history(databases, monkeypatch, capsys):
    repo, _managed, override, _active, gateway = databases
    before = _cache_snapshot(repo)
    monkeypatch.setattr(chat_cli.sys, "stdin", io.StringIO(f"{QUESTION}\n{QUESTION}\n"))
    assert chat_cli.main(["--interactive", "--json", "--db-path", str(override)]) == 0
    responses = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(responses) == 2
    assert all(item["metadata"]["dataset_version_id"] is None for item in responses)
    assert all(item["metadata"]["turn_id"] is None for item in responses)
    assert repo.list_conversations() == []
    assert _cache_snapshot(repo) == before
    gateway.complete.assert_not_awaited()


def test_local_model_override_is_effective_and_never_persisted(databases, monkeypatch, capsys):
    repo, _managed, _override, _active, gateway = databases
    repo.set_provider_config({"provider": "groq", "mode": "remote_planning"})
    saved = repo.get_provider_config()
    received = []

    def configured_gateway(config):
        received.append(dict(config))
        return gateway

    monkeypatch.setattr(chat_cli, "get_gateway_for_config", configured_gateway)
    assert chat_cli.main(["--question", QUESTION, "--local-model", "installed-model"]) == 0
    capsys.readouterr()
    assert received[0]["provider"] == "local"
    assert received[0]["mode"] == "local_only"
    assert received[0]["model"] == received[0]["litert_model"] == "installed-model"
    assert received[0]["base_url"] == saved["litert_base_url"]
    assert repo.get_provider_config() == saved
    gateway.complete.assert_not_awaited()


def test_interactive_session_resets_context_on_import_change(databases, monkeypatch, capsys):
    import asyncio

    repo, _managed, _override, active, gateway = databases
    conversation = repo.create_conversation("Existing import", active.id)
    session = chat_cli._ChatSession(
        conversation_id=conversation, parent_turn_id="obsolete-turn", dataset_version_id="older-id"
    )
    response = asyncio.run(chat_cli._ask_question(QUESTION, session=session))
    assert session.conversation_id != conversation
    assert session.dataset_version_id == active.id
    assert session.parent_turn_id == response.metadata.turn_id
    assert repo.get_turns(conversation) == []
    assert len(repo.get_turns(session.conversation_id)) == 1
    assert "import changed" in capsys.readouterr().err
    gateway.complete.assert_not_awaited()


def test_interrupted_turn_leaves_no_pending_history(databases, monkeypatch):
    import asyncio

    repo, _managed, _override, _active, _gateway = databases

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(chat_cli.ChatOrchestrator, "answer", cancelled)
    session = chat_cli._ChatSession()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(chat_cli._ask_question(QUESTION, session=session))
    turns = repo.get_turns(session.conversation_id)
    # The session transaction rolls back the pending turn on cancellation.
    assert turns == []


def test_loop_can_answer_a_complete_question_after_a_fallback(databases, monkeypatch, capsys):
    repo, _managed, _override, _active, gateway = databases
    monkeypatch.setattr(
        chat_cli.sys, "stdin", io.StringIO(f"Top 5 runs by pace\n{QUESTION}\n/quit\n")
    )
    assert chat_cli.main(["--interactive", "--json"]) == 0
    responses = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["template_id"] for item in responses] == ["fallback", "workout_card"]
    conversation = repo.list_conversations()[0]
    assert len(repo.get_turns(conversation["id"])) == 2
    gateway.complete.assert_not_awaited()


async def _ask_channel(channel, gateway, question, **options):
    if channel == "cli":
        return await chat_cli._ask_question(question, **options)
    app = create_app()
    app.dependency_overrides[_get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"question": question, **options})
    assert result.status_code == 200
    return ChatResponse.model_validate(result.json())


@pytest.mark.parametrize("channel", ["http", "cli"])
@pytest.mark.parametrize("kind", ["exact", "canonical", "history"])
async def test_pre_fix_scoped_answers_cannot_bypass_corrected_planning(
    databases, monkeypatch, channel, kind
):
    repo, managed, _override, active, gateway = databases
    question = "Show daily steps from 2026-06-01 to 2026-06-03"
    correct = await chat_cli._ask_question(question, cache_mode="fresh")
    wrong = await chat_cli._ask_question("Show daily steps", cache_mode="fresh")
    assert correct.data != wrong.data
    with duckdb.connect(str(managed), read_only=True) as conn:
        plan = plan_local_question(question, get_data_profile(conn))
    assert plan is not None
    # v8 history could contain an incorrect semantic reuse recorded against
    # the requested plan. Equal arguments alone cannot establish trust.
    old_plan = {**plan, "snapshot_contract": "leased-generation-v1"}
    if kind == "history":
        conversation = repo.create_conversation("Synthetic old scope", active.id)
        turn = repo.add_completed_turn(
            conversation,
            question,
            wrong.model_dump_json(),
            "default",
            "cached",
            canonical_plan=old_plan,
        )
        before = repo.get_turn(turn)
    else:
        with monkeypatch.context() as patch:
            patch.setattr(cache_keys, "CACHE_KEY_VERSION", "chat-cache-v8")
            patch.setattr(cache_keys, "PLANNER_CONTRACT", "typed-plan-v2")
            key = cache_keys.build_cache_key(
                kind,
                question if kind == "exact" else plan,
                generation_identity=cache_keys.generation_identity(repo.get_provider_config()),
            )
        repo.put_cached_response(key, active.id, wrong.model_dump_json(), canonical_plan=plan)
        before = _cache_snapshot(repo)

    result = await _ask_channel(channel, gateway, question)
    assert result.data == correct.data
    assert result.metadata.provenance == "deterministic_local"
    if kind == "history":
        assert repo.get_turn(turn) == before  # Preserve the old transcript unchanged.
    else:
        assert all(row in _cache_snapshot(repo) for row in before)
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize("channel", ["http", "cli"])
async def test_current_scoped_intents_reuse_exact_and_canonical_answers(databases, channel):
    repo, _managed, _override, _active, gateway = databases
    question = "Show daily steps from 2026-06-01 to 2026-06-03"
    first = await _ask_channel(channel, gateway, question)
    exact = await _ask_channel(channel, gateway, question)
    equivalent = await _ask_channel(
        channel, gateway, "Please show daily steps between 2026-06-01 and 2026-06-03"
    )
    assert first.metadata.provenance == "deterministic_local"
    assert exact.metadata.provenance == equivalent.metadata.provenance == "cached"
    assert first.data == exact.data == equivalent.data
    # Synthetic cache removal exercises history independently of exact/canonical.
    conversation = repo.create_conversation(
        "Synthetic current scope", first.metadata.dataset_version_id
    )
    await _ask_channel(channel, gateway, question, conversation_id=conversation)
    repo.clear_cache()
    if channel == "http":
        semantic = await _ask_channel(channel, gateway, question)
        assert semantic.metadata.provenance == "semantic_cached"
        assert semantic.data == first.data
    gateway.complete.assert_not_awaited()


@pytest.mark.parametrize("channel", ["http", "cli"])
@pytest.mark.parametrize("legacy", [False, True])
async def test_selected_parent_contract_and_scoped_cache_precedence(databases, channel, legacy):
    repo, _managed, _override, active, gateway = databases
    conversation = repo.create_conversation("Synthetic scoped parent", active.id)
    parent = await _ask_channel(
        channel,
        gateway,
        "Show weekly steps from 2026-06-01 to 2026-06-03",
        conversation_id=conversation,
    )
    # Warm the generic 90-day daily plan that must not replace the selected scope.
    await _ask_channel(channel, gateway, "Show daily steps")
    if legacy:
        with repo.session() as store:
            row = repo.get_turn(parent.metadata.turn_id, conn=store)
            plan = json.loads(row["canonical_plan_json"])
            del plan["planner_contract"]
            store.execute(
                "UPDATE turns SET canonical_plan_json = ? WHERE id = ?",
                [json.dumps(plan), parent.metadata.turn_id],
            )
    result = await _ask_channel(
        channel,
        gateway,
        "Show steps daily instead",
        conversation_id=conversation,
        parent_turn_id=parent.metadata.turn_id,
    )
    if legacy:
        assert result.template_id == "fallback"
        assert result.data["reason"] == "clarification_needed"
    else:
        assert result.template_id == "trend_chart"
        assert len(result.data["series"]) == 3
    gateway.complete.assert_not_awaited()
