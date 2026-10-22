"""Final safety review regressions: actual worker lifetime and proven retirement."""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.connection import dataset_snapshot
from app.db.dataset_lifecycle import DatasetLifecycle
from app.llm import orchestrator as orchestrator_module
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import CHILD, _child, _env
from tests.integration.test_dataset_snapshots import duration, exports


@pytest.fixture
def safety_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(tmp_path / "shards"))
    sources = exports(tmp_path)
    _child(tmp_path, "import", sources[0])
    return DatasetLifecycle(), AppStateRepository(), sources


@pytest.mark.parametrize("branch", ["local", "remote", "preparation"])
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_cancelled_http_worker_keeps_snapshot_until_actual_exit(
    safety_dataset, monkeypatch, branch, worker_fails
):
    from app.api import chat
    from app.main import create_app

    lifecycle, repo, _ = safety_dataset
    active = lifecycle.active()
    conversation = repo.create_conversation("Cancelled worker", active.dataset.id)
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    connections, values, failures = [], [], []
    real_dispatch = orchestrator_module.ChatOrchestrator._dispatch_tool
    real_profile = chat.get_data_profile

    def run_blocked(conn, operation):
        connections.append(conn)
        entered.set()
        assert release.wait(10)
        try:
            values.append(conn.execute("SELECT count(*) FROM workouts").fetchone()[0])
            if worker_fails:
                raise RuntimeError("synthetic worker failure")
            return operation()
        except Exception as exc:
            failures.append(exc)
            raise
        finally:
            exited.set()

    def blocked_dispatch(self, *args):
        return run_blocked(self.conn, lambda: real_dispatch(self, *args))

    def blocked_profile(conn):
        return run_blocked(conn, lambda: real_profile(conn))

    if branch == "preparation":
        monkeypatch.setattr(chat, "get_data_profile", blocked_profile)
    else:
        monkeypatch.setattr(
            orchestrator_module.ChatOrchestrator, "_dispatch_tool", blocked_dispatch
        )
    planner = AsyncMock(
        return_value=json.dumps(
            {"tool_name": "get_last_workout", "arguments": {"activity_type": "Running"}}
        )
    )
    if branch == "remote":
        monkeypatch.setattr(chat, "plan_local_question", lambda *args: None)
        monkeypatch.setattr(orchestrator_module, "plan_local_question", lambda *args: None)
        monkeypatch.setattr(orchestrator_module.ChatOrchestrator, "_complete_provider", planner)
    gateway = Mock(client=object(), model="denied")
    gateway.complete = AsyncMock(side_effect=AssertionError("provider execution denied"))
    app = create_app()
    app.dependency_overrides[chat._get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        task = asyncio.create_task(
            client.post(
                "/api/chat",
                json={
                    "question": "Show my last run",
                    "cache_mode": "fresh",
                    "conversation_id": conversation,
                },
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            for _ in range(2):
                task.cancel()
                # A real HTTP request yields the loop and exercises physical
                # deletion while the actual DB worker is still behind its barrier.
                deletion = await client.request(
                    "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
                )
                assert deletion.status_code == 409
                assert not task.done()
                assert not exited.is_set()
                assert lifecycle.generation_is_leased(active.dataset.id)
                assert active.database_path.exists()
                assert connections[0].execute("SELECT count(*) FROM workouts").fetchone() == (3,)
                assert (await client.get("/health")).status_code == 200
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
            assert await asyncio.to_thread(exited.wait, 10)
        assert values == [3]
        assert all(str(exc) == "synthetic worker failure" for exc in failures)
        assert len(failures) == int(worker_fails)
        assert not lifecycle.generation_is_leased(active.dataset.id)
        with pytest.raises(duckdb.ConnectionException, match="closed"):
            connections[0].execute("SELECT 1")
        turns = repo.get_turns(conversation)
        assert [turn["state"] for turn in turns] == ["cancelled"]
        assert not repo.finish_turn(turns[0]["id"], response_json="{}", cache_outcome="miss")
        assert (
            await client.request(
                "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
            )
        ).status_code == 200
    assert not active.database_path.exists()
    gateway.complete.assert_not_awaited()
    assert planner.await_count == int(branch == "remote")


@pytest.mark.parametrize("worker_fails", [False, True])
async def test_standalone_orchestrator_profile_drains_before_snapshot_exit(
    safety_dataset, monkeypatch, worker_fails
):
    lifecycle, _, _ = safety_dataset
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    connections, values = [], []
    real_profile = orchestrator_module.get_data_profile

    def blocked_profile(conn):
        connections.append(conn)
        entered.set()
        assert release.wait(10)
        try:
            values.append(conn.execute("SELECT count(*) FROM workouts").fetchone()[0])
            if worker_fails:
                raise RuntimeError("synthetic profile failure")
            return real_profile(conn)
        finally:
            exited.set()

    monkeypatch.setattr(orchestrator_module, "get_data_profile", blocked_profile)

    async def answer():
        with dataset_snapshot() as snapshot:
            return await orchestrator_module.ChatOrchestrator(
                client=Mock(), conn=snapshot.connection
            ).answer("Show my last run")

    task = asyncio.create_task(answer())
    active = lifecycle.active()
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        for _ in range(2):
            task.cancel()
            # FIFO event-loop barrier: cancellation is delivered before this
            # callback, with no wall-clock sleep or scheduling assumption.
            barrier = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(barrier.set_result, None)
            await barrier
            assert not task.done()
            assert lifecycle.generation_is_leased(active.dataset.id)
            assert connections[0].execute("SELECT 1").fetchone() == (1,)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 10)
        assert await asyncio.to_thread(exited.wait, 10)
    assert values == [3]
    assert not lifecycle.generation_is_leased(active.dataset.id)
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.parametrize("endpoint", ["summary", "workouts", "workouts/1"])
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_cancelled_dashboard_worker_retains_borrowed_snapshot(
    safety_dataset, monkeypatch, endpoint, worker_fails
):
    from app.api import dashboard
    from app.main import create_app

    lifecycle, _, _ = safety_dataset
    active = lifecycle.active()
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    values = []
    real_context = dashboard.resolve_dashboard_context

    def blocked(conn, repo):
        entered.set()
        assert release.wait(10)
        try:
            values.append(conn.execute("SELECT count(*) FROM workouts").fetchone()[0])
            if worker_fails:
                raise RuntimeError("synthetic dashboard failure")
            return real_context(conn, repo)
        finally:
            exited.set()

    monkeypatch.setattr(dashboard, "resolve_dashboard_context", blocked)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        task = asyncio.create_task(client.get(f"/api/dashboard/{endpoint}"))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            for _ in range(2):
                task.cancel()
                response = await client.request(
                    "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
                )
                assert response.status_code == 409
                assert not task.done()
                assert lifecycle.generation_is_leased(active.dataset.id)
                assert active.database_path.exists()
                assert (await client.get("/health")).status_code == 200
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
            assert await asyncio.to_thread(exited.wait, 10)
        assert values == [3]
        assert not lifecycle.generation_is_leased(active.dataset.id)
        assert (
            await client.request(
                "DELETE", "/api/settings/health", json={"confirm": True, "scope": "health"}
            )
        ).status_code == 200


def test_sequential_official_imports_retire_idle_committed_copies(safety_dataset, tmp_path):
    lifecycle, repo, sources = safety_dataset
    ids = []
    for source, expected in zip(
        [sources[0], *sources[1:], sources[0]], [45.5, 999, 321, 45.5], strict=True
    ):
        if ids:
            _child(tmp_path, "import", source)
        with dataset_snapshot() as snapshot:
            ids.append(snapshot.dataset.id)
            assert duration(snapshot) == expected
            assert snapshot.export_root == source.parent
        for _ in range(2):
            lifecycle.recover(repo)
    with lifecycle.writer_lock():
        protected = lifecycle.protected_generation_ids()
    remaining = {p.name for p in (lifecycle.root / "generations").iterdir() if p.is_dir()}
    assert remaining == protected == set(ids[-2:])
    assert all((lifecycle.root / "leases" / f"{key}.lock").is_file() for key in ids)


def test_reader_release_while_publication_holds_writer_lock_is_retried(
    safety_dataset, tmp_path, monkeypatch
):
    lifecycle, repo, sources = safety_dataset
    entered, release = threading.Event(), threading.Event()

    def reader():
        with dataset_snapshot() as snapshot:
            entered.set()
            assert release.wait(10)
            assert duration(snapshot) == 45.5

    old = lifecycle.active()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reader)
        try:
            assert entered.wait(10)
            _child(tmp_path, "import", sources[1])
            assert old.database_path.exists()
            read_fd, write_fd = os.pipe()
            code = CHILD.replace(
                "    if name == os.environ.get('CRASH_BOUNDARY'):",
                "    if name == 'retained_committed':\n"
                f"        os.write({write_fd}, b'publication-locked')\n"
                "        assert sys.stdin.readline().strip() == 'release'\n"
                "    if name == os.environ.get('CRASH_BOUNDARY'):",
            )
            publisher = subprocess.Popen(  # noqa: S603
                [sys.executable, "-c", code, "import", str(sources[2])],
                env=_env(tmp_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                pass_fds=(write_fd,),
            )
            os.close(write_fd)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(read_fd, selectors.EVENT_READ)
                    assert selector.select(10)
                assert os.read(read_fd, 64) == b"publication-locked", publisher.communicate(
                    timeout=10
                )
                release.set()
                future.result(10)  # Teardown's nonblocking writer attempt loses.
                assert old.database_path.exists()
                _, errors = publisher.communicate("release\n", timeout=10)
                assert publisher.returncode == 0, errors
            finally:
                os.close(read_fd)
                if publisher.poll() is None:
                    publisher.kill()
                    publisher.communicate(timeout=10)
        finally:
            release.set()
            future.result(10)
    for _ in range(2):
        lifecycle.recover(repo)
    assert not old.database_path.exists()
    assert lifecycle.active().export_root == sources[2].parent


RETIREMENT_BOUNDARIES = (
    "retirement_candidate_written",
    "retirement_candidate_fsynced",
    "retirement_candidate_replaced",
    "retirement_candidate_committed",
    "retained_written",
    "retained_fsynced",
    "retained_replaced",
    "retained_committed",
    "journal_unlinked",
    "journal_removed",
    "retirement_cleanup_started",
    "deletion_database_unlinked",
    "generation_manifest_unlinked",
    "generation_directory_removed",
    "retirement_generation_removed",
    "retirement_drained_written",
    "retirement_drained_fsynced",
    "retirement_drained_replaced",
    "retirement_drained_committed",
)


@pytest.mark.parametrize("boundary", RETIREMENT_BOUNDARIES)
def test_retirement_process_death_replays_exact_candidate(safety_dataset, tmp_path, boundary):
    lifecycle, repo, sources = safety_dataset
    oldest = lifecycle.active()
    _child(tmp_path, "import", sources[1])
    rollback = lifecycle.active()
    _child(tmp_path, "import", sources[2], boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        with dataset_snapshot() as snapshot:
            assert duration(snapshot) == 321
            assert snapshot.export_root == sources[2].parent
            assert snapshot.dataset == repo.get_active()
        assert not oldest.database_path.exists()
        assert rollback.database_path.exists()
        assert (lifecycle.root / "leases" / f"{oldest.dataset.id}.lock").is_file()
    assert json.loads((lifecycle.root / "retirement.json").read_text())["generations"] == []
    assert all((source.parent / "sentinel").is_file() for source in sources)


@pytest.mark.parametrize("boundary", RETIREMENT_BOUNDARIES[10:])
def test_retirement_startup_can_die_again_without_losing_proof(safety_dataset, tmp_path, boundary):
    lifecycle, repo, sources = safety_dataset
    oldest = lifecycle.active()
    _child(tmp_path, "import", sources[1])
    rollback = lifecycle.active()
    _child(tmp_path, "import", sources[2], boundary="retirement_candidate_committed", expected=73)
    _child(tmp_path, "startup", boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        with dataset_snapshot() as snapshot:
            assert snapshot.dataset == repo.get_active()
            assert snapshot.export_root == sources[2].parent
            assert duration(snapshot) == 321
        assert rollback.database_path.exists()
        assert not oldest.database_path.exists()


def leave_pending_retirement(lifecycle, tmp_path, sources):
    """Release a superseded reader while the writer excludes its teardown."""
    context = dataset_snapshot()
    snapshot = context.__enter__()
    _child(tmp_path, "import", sources[1])
    _child(tmp_path, "import", sources[2])
    with lifecycle.writer_lock():
        context.__exit__(None, None, None)
    return snapshot.database_path


@pytest.mark.parametrize(
    "boundary",
    [
        "retirement_cleanup_started",
        "deletion_database_unlinked",
        "generation_manifest_unlinked",
        "generation_directory_removed",
        "retirement_drained_written",
        "retirement_drained_replaced",
    ],
)
def test_cleanup_io_failure_and_repeated_recovery_remain_retryable(
    safety_dataset, tmp_path, monkeypatch, boundary
):
    lifecycle, repo, sources = safety_dataset
    old_path = leave_pending_retirement(lifecycle, tmp_path, sources)
    faults = []

    def fail(self, name):
        if name == boundary and not faults:
            faults.append(name)
            raise OSError("synthetic cleanup IO failure")

    with monkeypatch.context() as patch:
        patch.setattr(DatasetLifecycle, "_boundary", fail)
        assert lifecycle.recover(repo).export_root == sources[2].parent
    assert faults == [boundary]
    for _ in range(2):
        lifecycle.recover(repo)
    assert not old_path.exists()
    assert json.loads((lifecycle.root / "retirement.json").read_text())["generations"] == []


@pytest.mark.parametrize("change", ["manifest", "database", "extra", "replaced", "symlink"])
def test_retirement_preserves_changed_or_unknown_contents(safety_dataset, tmp_path, change):
    lifecycle, repo, sources = safety_dataset
    path = leave_pending_retirement(lifecycle, tmp_path, sources)
    if change == "manifest":
        path.with_name("manifest.json").write_text("changed unknown manifest")
    elif change == "database":
        with path.open("ab") as output:
            output.write(b"changed contents")
    elif change == "extra":
        path.with_name("caller-sentinel").write_text("preserve")
    else:
        saved = path.parent.with_name("caller-saved")
        path.parent.rename(saved)
        if change == "replaced":
            shutil.copytree(saved, path.parent)
        else:
            path.parent.symlink_to(saved, target_is_directory=True)
    for _ in range(2):
        assert lifecycle.recover(repo).export_root == sources[2].parent
        assert path.exists()
        assert len(json.loads((lifecycle.root / "retirement.json").read_text())["generations"]) == 1


def test_unknown_retirement_record_blocks_import_without_claiming_old_allocations(
    safety_dataset, tmp_path
):
    from app.db.dataset_lifecycle import DatasetRecoveryError

    lifecycle, repo, sources = safety_dataset
    active = lifecycle.active()
    record = lifecycle.root / "retirement.json"
    record.write_text('{"format_version":99,"generations":[]}')
    with pytest.raises(DatasetRecoveryError):
        lifecycle.recover(repo)
    result = _child(tmp_path, "import", sources[1], expected=1)
    assert result.returncode == 1
    assert lifecycle.active() == active
    assert record.read_text() == '{"format_version":99,"generations":[]}'


def test_old_store_without_retirement_record_preserves_unproven_generations(
    safety_dataset, tmp_path
):
    lifecycle, repo, sources = safety_dataset
    original = lifecycle.active()
    # An interrupted precommit publication is complete but has never been a
    # retained committed pointer. A matching filename/manifest is insufficient.
    _child(tmp_path, "import", sources[1], boundary="generation_fsynced", expected=73)
    allocated = {p.name for p in (lifecycle.root / "generations").iterdir()}
    for _ in range(2):
        lifecycle.recover(repo)
    _child(tmp_path, "import", sources[2])
    _child(tmp_path, "import", sources[0])
    remaining = {p.name for p in (lifecycle.root / "generations").iterdir()}
    assert allocated - {original.dataset.id} <= remaining
    assert not original.database_path.exists()
