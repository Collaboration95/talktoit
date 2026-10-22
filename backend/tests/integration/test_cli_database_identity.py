"""Real headless cache regressions using two synthetic health databases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest

from app.cli import chat as chat_cli
from app.ingest.coordinator import ingest_v2
from app.llm.provider_gateway import ProviderUnavailableError
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
    active = repo.activate(
        source_bytes=b"synthetic-a",
        source_size_bytes=1,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-06-01",
        coverage_end="2026-06-30",
        counts={"workouts": 3},
    )
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
