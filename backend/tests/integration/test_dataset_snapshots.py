"""Generation identity and deletion races using synthetic imports and barriers."""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import CHILD, _child, _env

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def exports(tmp_path):
    result = []
    for name, duration, latitude in (
        ("a", 45.5, "1.3521"),
        ("b", 999, "2.3521"),
        ("c", 321, "3.3521"),
    ):
        root = tmp_path / name
        routes = root / "workout-routes"
        routes.mkdir(parents=True)
        xml = root / "export.xml"
        xml.write_text(
            (FIXTURES / "sample.xml")
            .read_text()
            .replace('duration="45.5"', f'duration="{duration}"')
        )
        gpx = (FIXTURES / "route.gpx").read_text().replace("1.3521", latitude)
        for route in ("route_2026-06-05_7.00am.gpx", "route_2026-06-08_6.00pm.gpx"):
            (routes / route).write_text(gpx)
        (root / "sentinel").write_text(name)
        result.append(xml)
    return result


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    for key, value in _env(tmp_path).items():
        if key.startswith("TTI_"):
            monkeypatch.setenv(key, value)
    sources = exports(tmp_path)
    _child(tmp_path, "import", sources[0])
    return DatasetLifecycle(), AppStateRepository(), sources


def duration(snapshot):
    return snapshot.connection.execute(
        "SELECT duration FROM workouts WHERE activity_type = 'Running'"
    ).fetchone()[0]


def test_pointer_change_during_acquisition_retries_whole_tuple(dataset, tmp_path, monkeypatch):
    from app.db.connection import dataset_snapshot

    lifecycle, _, sources = dataset
    entered, release = threading.Event(), threading.Event()
    calls = []

    def barrier(self, name):
        if name == "snapshot_pointer_read" and not calls:
            calls.append(name)
            entered.set()
            assert release.wait(10)

    monkeypatch.setattr(DatasetLifecycle, "_boundary", barrier)

    def read():
        with dataset_snapshot() as snapshot:
            return duration(snapshot), snapshot.dataset.id, snapshot.export_root

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(read)
        try:
            assert entered.wait(10)
            _child(tmp_path, "import", sources[1])
        finally:
            release.set()
        value, identity, root = future.result(10)
    assert value == 999
    assert identity == lifecycle.active().dataset.id
    assert root == sources[1].parent


def test_leased_reader_survives_replacements_and_retirement(dataset, tmp_path):
    from app.db.connection import dataset_snapshot

    lifecycle, _, sources = dataset
    with dataset_snapshot() as snapshot:
        old = snapshot.dataset.id
        old_path = snapshot.database_path
        _child(tmp_path, "import", sources[1])
        _child(tmp_path, "import", sources[2])
        assert duration(snapshot) == 45.5
        assert snapshot.export_root == sources[0].parent
        assert not lifecycle.retire_generation(old, timeout=0)
        assert old_path.exists()
    lifecycle.retire_generation(old, timeout=0)
    assert not old_path.exists()
    assert lifecycle.active().dataset.id != old
    with dataset_snapshot() as current:
        assert duration(current) == 321


LEASE_CHILD = """
import json, sys
from app.db.connection import dataset_snapshot
with dataset_snapshot() as snapshot:
    print(json.dumps({'id':snapshot.dataset.id}), flush=True)
    assert sys.stdin.readline().strip() == 'release'
    value = snapshot.connection.execute(
        "SELECT duration FROM workouts WHERE activity_type = 'Running'").fetchone()[0]
    print(json.dumps({'duration':value}), flush=True)
"""


def test_cross_process_lease_blocks_unlink_but_not_tombstone(dataset, tmp_path):
    from app.db.connection import dataset_snapshot
    from app.db.dataset_lifecycle import DatasetBusyError

    lifecycle, repo, sources = dataset
    active = lifecycle.active()
    repo.create_conversation("Keep history", active.dataset.id)
    repo.put_cached_response("unrelated", "other", '{"a":1}')
    child = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", LEASE_CHILD],
        env=_env(tmp_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(10), "reader did not acquire its lease"
        assert json.loads(child.stdout.readline())["id"] == active.dataset.id
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0.03)
        assert lifecycle.active() is None
        assert repo.get_active() is None
        assert repo.get_export_root() is None
        assert active.database_path.exists()
        with dataset_snapshot() as empty:
            assert empty.dataset is None
            assert empty.export_root is None
            assert empty.connection.execute("SELECT count(*) FROM workouts").fetchone() == (0,)
        output, errors = child.communicate("release\n", timeout=10)
        assert child.returncode == 0, errors
        assert json.loads(output)["duration"] == 45.5
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)
    lifecycle.delete(repo, timeout=0.1)
    for _ in range(2):
        assert lifecycle.recover(repo) is None
    assert not active.database_path.exists()
    assert repo.count_conversations() == 1
    assert repo.get_cached_entry("unrelated", "other") is not None
    assert (sources[0].parent / "sentinel").read_text() == "a"


def test_import_delete_serialize_on_same_process_lock(dataset, tmp_path):
    from app.db.dataset_lifecycle import DatasetBusyError

    lifecycle, repo, sources = dataset
    # This lock is held in another process while import would own it.
    code = """
import sys
from app.db.dataset_lifecycle import DatasetLifecycle
with DatasetLifecycle().writer_lock():
    print('locked', flush=True)
    assert sys.stdin.readline().strip() == 'release'
"""
    command = [sys.executable, "-c", code]
    child = subprocess.Popen(  # noqa: S603
        command,
        env=_env(tmp_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(10)
        assert child.stdout.readline().strip() == "locked"
        old = lifecycle.active().dataset.id
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0.03)
        assert lifecycle.active().dataset.id == old
        child.communicate("release\n", timeout=10)
        assert child.returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)
    lifecycle.delete(repo, timeout=0.1)
    _child(tmp_path, "import", sources[1])
    assert lifecycle.recover(repo).export_root == sources[1].parent
    lifecycle.delete(repo, timeout=0.1)
    assert lifecycle.recover(repo) is None


@pytest.mark.asyncio
async def test_chat_and_route_use_leased_identity_during_import(dataset, tmp_path, monkeypatch):
    from app.api import chat, dashboard
    from app.main import create_app

    lifecycle, repo, sources = dataset
    old = lifecycle.active().dataset.id
    entered, release = threading.Event(), threading.Event()
    real_prepare = chat._prepare_chat

    def barrier(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(chat, "_prepare_chat", barrier)
    gateway = Mock(client=object(), model="stub")
    gateway.complete = AsyncMock(side_effect=AssertionError("no provider"))
    app = create_app()
    app.dependency_overrides[chat._get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task = asyncio.create_task(client.post("/api/chat", json={"question": "Show my last run"}))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            await asyncio.to_thread(_child, tmp_path, "import", sources[1])
        finally:
            release.set()
        answer = (await asyncio.wait_for(task, 10)).json()
        assert answer["data"]["duration_minutes"] == 45.5
        assert answer["metadata"]["dataset_version_id"] == old
        current = lifecycle.active().dataset.id
        next_answer = (await client.post("/api/chat", json={"question": "Show my last run"})).json()
        assert next_answer["data"]["duration_minutes"] == 999
        assert next_answer["metadata"]["dataset_version_id"] == current

        real_context = dashboard.resolve_dashboard_context

        def import_during_route(conn, repository):
            context = real_context(conn, repository)
            _child(tmp_path, "import", sources[2])
            return context

        monkeypatch.setattr(dashboard, "resolve_dashboard_context", import_during_route)
        detail = (await client.get("/api/dashboard/workouts/1")).json()
        assert detail["duration_minutes"] == 999
        assert detail["resource"]["dataset_version_id"] == current
        assert detail["gps_route"]["coordinates"][0][1] == 2.3521
    assert repo.get_active().id == lifecycle.active().dataset.id


@pytest.mark.asyncio
async def test_empty_onboarding_and_repeated_startup_have_no_identity(tmp_path, monkeypatch):
    from app import main
    from app.api import chat, settings

    for key, value in _env(tmp_path).items():
        if key.startswith("TTI_"):
            monkeypatch.setenv(key, value)

    async def no_provider(app):
        pass

    monkeypatch.setattr(main, "_maybe_autostart_litert", no_provider)
    monkeypatch.setattr(main, "make_provider_gateway", lambda: object())
    monkeypatch.setattr(settings, "_local_readiness", lambda config: {})
    gateway = Mock(client=object(), model="denied")
    gateway.complete = AsyncMock(side_effect=AssertionError("empty data must stay local"))
    for _ in range(2):
        app = main.create_app()
        app.dependency_overrides[chat._get_gateway] = lambda: gateway
        async with main._lifespan(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/status")).json()["dataset"] is None
                body = (await client.get("/api/settings")).json()
                assert body["dataset"] is None
                assert set(body["quality"]["metric_states"].values()) == {"unavailable"}
                workouts = (await client.get("/api/dashboard/workouts")).json()
                assert workouts["resource"]["dataset_version_id"] is None
                assert workouts["workouts"] == []
                summary = await client.get("/api/dashboard/summary")
                assert summary.status_code == 200
                assert summary.json()["resource"]["dataset_version_id"] is None
                assert summary.json()["resource"]["state"] == "empty"
                answer = await client.post("/api/chat", json={"question": "Show my last run"})
                assert answer.status_code == 200
                assert answer.json()["data"]["reason"] == "no_matching_data"
                assert answer.json()["metadata"]["dataset_version_id"] is None
                assert "Settings" in answer.json()["narrative"]
                gateway.complete.assert_not_awaited()
        assert not (tmp_path / "health.duckdb").exists()


@pytest.mark.asyncio
async def test_failed_unlink_stays_inactive_and_preserves_other_scopes(dataset, monkeypatch):
    from app.main import create_app

    lifecycle, repo, _ = dataset
    active = lifecycle.active()
    repo.create_conversation("keep", active.dataset.id)
    real_unlink = os.unlink

    def fail(path, *args, **kwargs):
        if path == "health.duckdb" and kwargs.get("dir_fd") is not None:
            raise OSError("private path should not escape")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", fail)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.request(
            "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
        )
        assert response.status_code == 409
        assert "private path" not in response.text
        assert (await client.get("/api/status")).json()["dataset"] is None
    assert repo.get_active() is None
    assert active.database_path.exists()
    assert repo.count_conversations() == 1


@pytest.mark.parametrize(
    "boundary",
    [
        "deletion_intent_written",
        "deletion_intent_fsynced",
        "deletion_intent_replaced",
        "deletion_intent_committed",
        "deletion_journal_written",
        "deletion_journal_fsynced",
        "deletion_journal_replaced",
        "deletion_journal_committed",
        "deletion_pointer_written",
        "deletion_pointer_fsynced",
        "deletion_pointer_replaced",
        "deletion_pointer_committed",
        "deletion_projected",
        "retained_cleared",
        "journal_unlinked",
        "deletion_database_unlinked",
        "deletion_finished",
    ],
)
def test_hard_exit_during_deletion_never_resurrects(dataset, tmp_path, boundary):
    lifecycle, repo, sources = dataset
    code = CHILD.replace(
        "if sys.argv[1] == 'import':",
        """if sys.argv[1] == 'delete':
    DatasetLifecycle().delete(AppStateRepository())
elif sys.argv[1] == 'import':""",
    )
    command = [sys.executable, "-c", code, "delete"]
    result = subprocess.run(  # noqa: S603
        command,
        env={**_env(tmp_path), "CRASH_BOUNDARY": boundary},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 73, result.stderr
    committed = boundary in {
        "deletion_pointer_replaced",
        "deletion_pointer_committed",
        "deletion_projected",
        "retained_cleared",
        "journal_unlinked",
        "deletion_database_unlinked",
        "deletion_finished",
    }
    for _ in range(2):
        _child(tmp_path, "startup")
        assert (lifecycle.active() is None) == committed
        assert (repo.get_active() is None) == committed
    assert (sources[0].parent / "sentinel").read_text() == "a"


@pytest.mark.asyncio
async def test_new_generation_cannot_append_to_old_conversation(dataset, tmp_path):
    from app.api import chat
    from app.main import create_app

    lifecycle, repo, sources = dataset
    conversation = repo.create_conversation("Old import", lifecycle.active().dataset.id)
    _child(tmp_path, "import", sources[1])
    app = create_app()
    gateway = Mock(client=object(), model="stub")
    app.dependency_overrides[chat._get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json={"question": "Show my last run", "conversation_id": conversation}
        )
    assert response.status_code == 409
    assert "new conversation" in response.text.lower()
    assert repo.get_turns(conversation) == []


def test_unbound_connection_cannot_borrow_managed_identity(dataset):
    import duckdb

    from app.db.connection import connection_dataset

    _, repo, _ = dataset
    with duckdb.connect(":memory:") as unbound:
        assert connection_dataset(unbound, repo) is None


@pytest.mark.asyncio
async def test_previous_cache_contract_cannot_replay_mislabeled_generation(dataset, tmp_path):
    from app.api import chat
    from app.llm import cache_keys
    from app.main import create_app

    lifecycle, repo, sources = dataset
    app = create_app()
    app.dependency_overrides[chat._get_gateway] = lambda: Mock(client=object(), model="stub")
    question = "Show my last run"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer_a = (await client.post("/api/chat", json={"question": question})).json()
        _child(tmp_path, "import", sources[1])
        active_b = lifecycle.active().dataset.id
        from unittest.mock import patch

        with patch.object(cache_keys, "CACHE_KEY_VERSION", "chat-cache-v4"):
            key = cache_keys.build_cache_key(
                "exact",
                question,
                generation_identity=cache_keys.generation_identity(repo.get_provider_config()),
            )
        # The previous runtime could label an A answer with B after a swap.
        repo.put_cached_response(key, active_b, json.dumps(answer_a))
        answer_b = (await client.post("/api/chat", json={"question": question})).json()
    assert answer_b["data"]["duration_minutes"] == 999
    assert answer_b["metadata"]["dataset_version_id"] == active_b


@pytest.mark.asyncio
async def test_legacy_semantic_history_cannot_replay_mislabeled_generation(dataset, tmp_path):
    from app.api import chat
    from app.main import create_app

    lifecycle, repo, sources = dataset
    app = create_app()
    app.dependency_overrides[chat._get_gateway] = lambda: Mock(client=object(), model="stub")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer_a = (await client.post("/api/chat", json={"question": "Show my last run"})).json()
        _child(tmp_path, "import", sources[1])
        active_b = lifecycle.active().dataset.id
        conversation = repo.create_conversation("Prior history", active_b)
        repo.add_completed_turn(
            conversation,
            "Show my last run",
            json.dumps(answer_a),
            "default",
            "deterministic_local",
            canonical_plan={
                "tool_name": "get_last_workout",
                "arguments": {"activity_type": "Running"},
            },
        )
        answer_b = (
            await client.post("/api/chat", json={"question": "Show me my most recent run"})
        ).json()
    assert answer_b["data"]["duration_minutes"] == 999
    assert answer_b["metadata"]["dataset_version_id"] == active_b


@pytest.mark.asyncio
async def test_official_generation_exposes_metric_states_for_chat_starters(dataset, monkeypatch):
    from app.api import settings
    from app.main import create_app

    lifecycle, _, _ = dataset
    assert not lifecycle.target.exists()
    monkeypatch.setattr(settings, "_local_readiness", lambda config: {})
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        result = await client.get("/api/settings")
    assert result.status_code == 200
    payload = result.json()
    assert payload["dataset"]["id"] == lifecycle.active().dataset.id
    assert payload["dataset"]["counts"]["workouts"] == 3
    for metric in ("steps", "resting_hr", "hrv", "sleep"):
        assert payload["quality"]["metric_states"][metric] == "available"


@pytest.mark.asyncio
async def test_startup_recovers_owned_jobs_without_unlinking_leased_deleted_data(
    dataset, monkeypatch
):
    from app import main
    from app.api import imports, settings
    from app.db.connection import dataset_snapshot
    from app.db.dataset_lifecycle import DatasetBusyError
    from app.state.import_artifacts import ImportOperation, JobRecord

    lifecycle, repo, _ = dataset
    operation = ImportOperation.create(lifecycle)
    operation.upload_path.write_text("<HealthData/>")
    abandoned = operation.new_directory("staging", lifecycle.root / "staging")
    (abandoned / "health.duckdb").write_bytes(b"partial")
    operation.save_job(
        JobRecord(
            id=operation.id,
            filename="synthetic.xml",
            state="running",
            progress=0,
            created_at="2026-10-22T00:00:00+00:00",
        )
    )
    operation.close()
    monkeypatch.setattr(imports, "import_jobs", imports.ImportJobManager())
    monkeypatch.setattr(main, "make_provider_gateway", lambda: object())

    async def no_provider(app):
        pass

    monkeypatch.setattr(main, "_maybe_autostart_litert", no_provider)
    monkeypatch.setattr(settings, "_local_readiness", lambda config: {})
    with dataset_snapshot() as old:
        database = old.database_path
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        for _ in range(2):
            app = main.create_app()
            async with main._lifespan(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    assert (await client.get("/api/status")).json()["dataset"] is None
                    job = (await client.get(f"/api/imports/{operation.id}")).json()
                    assert job["state"] == "failed"
                    assert job["progress"] == 0
            assert duration(old) == 45.5
            assert database.exists()
            assert not abandoned.exists()
            assert not operation.upload_path.exists()
    lifecycle.recover(repo)
    assert not database.exists()


@pytest.mark.asyncio
async def test_empty_cli_offers_import_guidance_without_touching_provider(tmp_path, monkeypatch):
    from app.cli import chat

    for key in ("TTI_DB_PATH", "TTI_APP_STATE_PATH"):
        monkeypatch.setenv(key, _env(tmp_path)[key])

    def forbidden(*args, **kwargs):
        pytest.fail("empty CLI must not access a provider")

    monkeypatch.setattr(chat, "_ensure_local_server", forbidden)
    monkeypatch.setattr(chat, "get_gateway_for_config", forbidden)
    response = await chat._ask_question("What should I look at?")
    assert response.template_id == "fallback"
    assert response.data["reason"] == "no_matching_data"
    assert response.metadata.dataset_version_id is None
    assert "Settings" in response.narrative
    assert not (tmp_path / "health.duckdb").exists()


@pytest.mark.asyncio
async def test_saved_view_scope_is_reconciled_under_writer_lock(dataset):
    from dataclasses import replace

    from app.main import create_app

    lifecycle, repo, _ = dataset
    active = lifecycle.active()
    stale = replace(active.dataset, id="ds_" + "f" * 32)
    repo.project_generation(stale, active.export_root)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        result = await client.post(
            "/api/saved-views", json={"title": "Steps", "query": {"metric": "steps"}}
        )
    assert result.status_code == 200
    assert repo.list_saved_views()[0]["dataset_version_id"] == active.dataset.id


@pytest.mark.asyncio
async def test_simultaneous_import_query_delete_has_serialized_outcome(
    dataset, tmp_path, monkeypatch
):
    from app.api import chat
    from app.main import create_app

    lifecycle, _, sources = dataset
    old_id = lifecycle.active().dataset.id
    entered, release = threading.Event(), threading.Event()
    prepare = chat._prepare_chat

    def pause(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return prepare(*args, **kwargs)

    monkeypatch.setattr(chat, "_prepare_chat", pause)
    app = create_app()
    app.dependency_overrides[chat._get_gateway] = lambda: Mock(client=object(), model="stub")
    script = """
import sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.ingest import run
def boundary(self, name):
    if name == 'generation_renamed':
        print('IMPORT_READY', flush=True)
        assert sys.stdin.readline().strip() == 'commit'
DatasetLifecycle._boundary = boundary
sys.argv = ['ingest', sys.argv[1], '--workers', '1']
run.main()
"""
    command = [sys.executable, "-c", script, str(sources[1])]
    child = subprocess.Popen(  # noqa: S603
        command,
        env=_env(tmp_path),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def ready():
        return any(line.strip() == "IMPORT_READY" for line in iter(child.stdout.readline, ""))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        query = asyncio.create_task(client.post("/api/chat", json={"question": "Show my last run"}))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            assert await asyncio.wait_for(asyncio.to_thread(ready), 10)
            blocked = await client.request(
                "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
            )
            assert blocked.status_code == 409
            assert lifecycle.active().dataset.id == old_id
            _, errors = await asyncio.to_thread(child.communicate, "commit\n", timeout=10)
            assert child.returncode == 0, errors
            deleted = await client.request(
                "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
            )
            assert deleted.status_code == 409  # A reader still holds its generation.
            assert lifecycle.active() is None
        finally:
            release.set()
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        answer = (await asyncio.wait_for(query, 10)).json()
        assert answer["metadata"]["dataset_version_id"] == old_id
        assert answer["data"]["duration_minutes"] == 45.5
        assert (await client.get("/api/status")).json()["dataset"] is None
        retry = await client.request(
            "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
        )
        assert retry.status_code == 200
        _child(tmp_path, "import", sources[2])
        final = (await client.post("/api/chat", json={"question": "Show my last run"})).json()
        assert final["data"]["duration_minutes"] == 321
        assert final["metadata"]["dataset_version_id"] == lifecycle.active().dataset.id


@pytest.mark.parametrize(
    "boundary", ["retained_written", "retained_fsynced", "retained_replaced", "retained_committed"]
)
def test_retained_pointer_interruption_preserves_last_good_copy(dataset, tmp_path, boundary):
    from app.db.connection import dataset_snapshot

    lifecycle, repo, sources = dataset
    old_id = lifecycle.active().dataset.id
    _child(tmp_path, "import", sources[1], boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        with dataset_snapshot() as snapshot:
            assert duration(snapshot) == 999
            assert snapshot.dataset.id == repo.get_active().id
            assert snapshot.export_root == sources[1].parent
        assert (lifecycle.root / "generations" / old_id / "health.duckdb").exists()
        with lifecycle.writer_lock():
            assert old_id in lifecycle.protected_generation_ids()


def test_unknown_retention_record_is_preserved_without_replacing_active_data(dataset, tmp_path):
    lifecycle, repo, sources = dataset
    active = lifecycle.active()
    retained = lifecycle.root / "retained.json"
    retained.write_text("caller-owned unknown record")
    command = [sys.executable, "-c", CHILD, "import", str(sources[1])]
    result = subprocess.run(  # noqa: S603
        command,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode != 0
    assert retained.read_text() == "caller-owned unknown record"
    assert lifecycle.active() == active
    assert repo.get_active() == active.dataset


def test_database_open_failure_releases_lease_and_returns_safe_error(dataset, monkeypatch):
    import duckdb

    from app.db import connection
    from app.db.dataset_lifecycle import DatasetRecoveryError

    lifecycle, _, _ = dataset
    active = lifecycle.active().dataset.id

    def fail(*args, **kwargs):
        raise duckdb.IOException("private path SELECT raw")

    monkeypatch.setattr(connection, "connect", fail)
    with pytest.raises(DatasetRecoveryError) as error:
        with connection.dataset_snapshot():
            pytest.fail("unreadable data must not be served")
    assert "SELECT" not in str(error.value)
    assert not lifecycle.generation_is_leased(active)


def test_health_deletion_preserves_unproven_legacy_source(tmp_path, monkeypatch):
    from app.db.dataset_lifecycle import DatasetBusyError

    # A configured legacy filename alone does not prove that its contents are
    # an imported health DB; an XML/GPX or unrelated caller file must survive.
    for key in ("TTI_DB_PATH", "TTI_APP_STATE_PATH"):
        monkeypatch.setenv(key, _env(tmp_path)[key])
    source = tmp_path / "health.duckdb"
    original = b"<HealthData>caller-owned synthetic export</HealthData>"
    source.write_bytes(original)
    lifecycle = DatasetLifecycle()
    repo = AppStateRepository()
    with pytest.raises(DatasetBusyError):
        lifecycle.delete(repo, timeout=0)
    assert source.read_bytes() == original
    assert lifecycle.active() is None
    assert repo.get_active() is None
