"""Real process-death evidence for the durable dataset commit protocol.

All exports, databases, route roots and sentinels are synthetic and temporary.
The child exits at synchronous boundaries; no sleep or Python cleanup can hide
an interrupted transaction.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from app.state.app_state import AppStateRepository

BOUNDARIES = (
    "staging_created",
    "database_closed",
    "database_fsynced",
    "manifest_written",
    "manifest_fsynced",
    "staging_fsynced",
    "generation_renamed",
    "generation_fsynced",
    "lease_fsynced",
    "journal_written",
    "journal_fsynced",
    "journal_committed",
    "pointer_written",
    "pointer_fsynced",
    "pointer_replaced",
    "pointer_committed",
    "projection_started",
    "projection_committed",
    "journal_unlinked",
    "journal_removed",
)
COMMITTED = BOUNDARIES[BOUNDARIES.index("pointer_replaced") :]
RECOVERY_BOUNDARIES = (
    "recovery_validated",
    "recovery_pointer_fsynced",
    "recovery_projected",
    "recovery_finished",
)

CHILD = """
import asyncio, os, signal, sys
from contextlib import contextmanager
from app.db.dataset_lifecycle import DatasetLifecycle
from app.ingest import run
from app.state.app_state import AppStateRepository

pointer_replaced = False
def boundary(self, name):
    global pointer_replaced
    if name == 'pointer_replaced':
        pointer_replaced = True
    if name == os.environ.get('CRASH_BOUNDARY'):
        if os.environ.get('FAULT_KIND') == 'sigkill':
            os.kill(os.getpid(), signal.SIGKILL)
        if os.environ.get('FAULT_KIND') == 'cancel':
            raise KeyboardInterrupt('synthetic cancellation')
        os._exit(73)
DatasetLifecycle._boundary = boundary
if os.environ.get('CRASH_BOUNDARY') == 'sqlite_transaction':
    original = AppStateRepository._connection
    @contextmanager
    def connection(self, *args, **kwargs):
        with original(self, *args, **kwargs) as conn:
            def trace(sql):
                if pointer_replaced and sql.startswith('INSERT INTO app_state'):
                    os._exit(73)
            conn.set_trace_callback(trace)
            yield conn
    AppStateRepository._connection = connection
if sys.argv[1] == 'import':
    sys.argv = ['ingest', sys.argv[2], '--workers', '1', '--report-json'] + sys.argv[3:]
    run.main()
elif sys.argv[1] == 'cli':
    from types import SimpleNamespace
    from app.cli import chat
    from app.models.chat import ChatResponse
    chat._ensure_local_server = lambda config: None
    chat.get_gateway_for_config = lambda config: SimpleNamespace(client=object(), model='stub')
    class Orchestrator:
        def __init__(self, **kwargs):
            self.value = kwargs['conn'].execute('SELECT min(value) FROM records').fetchone()[0]
        async def answer(self, question, **kwargs):
            return ChatResponse(template_id='fallback', narrative='Synthetic answer', data={
                'question':question, 'table':None, 'text':str(self.value)})
    chat.ChatOrchestrator = Orchestrator
    chat.main(['--question', 'Synthetic question', '--json', *sys.argv[2:]])
elif sys.argv[1] == 'startup':
    from app.main import create_app
    import app.main as main
    main.make_provider_gateway = lambda: object()
    async def no_provider(app): pass
    main._maybe_autostart_litert = no_provider
    main._maybe_stop_litert_on_exit = lambda: None
    async def start():
        app = create_app()
        async with main._lifespan(app): pass
    asyncio.run(start())
else:
    DatasetLifecycle().recover(AppStateRepository())
"""


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "TTI_DB_PATH": str(tmp_path / "health.duckdb"),
        "TTI_APP_STATE_PATH": str(tmp_path / "state.sqlite"),
        "TTI_LOCAL_AUTOSTART": "0",
    }


def _export(tmp_path: Path, name: str, value: int, count: int) -> Path:
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    export = root / "export.xml"
    record = (
        '<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Synthetic" '
        'startDate="2024-01-01 00:00:00 +0000" endDate="2024-01-01 00:01:00 +0000" '
        f'value="{value}"/>'
    )
    export.write_text("<HealthData>" + record * count + "</HealthData>")
    (root / "caller-owned.gpx").write_text(name)
    return export


def _child(tmp_path, mode, *args, boundary="", kind="exit", expected=0):
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CHILD, mode, *map(str, args)],
        env={**_env(tmp_path), "CRASH_BOUNDARY": boundary, "FAULT_KIND": kind},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return result


def _assert_tuple(tmp_path, expected_export, value, count):
    from app.db.dataset_lifecycle import DatasetLifecycle

    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    generation = lifecycle.active()
    repo = AppStateRepository(tmp_path / "state.sqlite")
    if expected_export is None:
        assert generation is None
        assert repo.get_active() is None
        assert repo.get_export_root() is None
        return None
    assert generation is not None
    assert generation.dataset == repo.get_active()
    assert generation.export_root == repo.get_export_root() == expected_export.parent.resolve()
    assert generation.dataset.counts["records"] == count
    assert generation.dataset.coverage_start == generation.dataset.coverage_end == "2024-01-01"
    with duckdb.connect(str(generation.database_path), read_only=True) as conn:
        assert conn.execute("SELECT count(*), min(value), max(value) FROM records").fetchone() == (
            count,
            value,
            value,
        )
    assert (expected_export.parent / "caller-owned.gpx").read_text() == expected_export.parent.name
    return generation.dataset.id


@pytest.mark.parametrize("replacement", [False, True], ids=["first", "replacement"])
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_hard_exit_at_every_activation_boundary(tmp_path, replacement, boundary):
    from app.db.dataset_lifecycle import DatasetLifecycle

    old = _export(tmp_path, "old-root", 42, 1)
    new = _export(tmp_path, "new-root", 999, 2)
    old_id = None
    if replacement:
        _child(tmp_path, "import", old)
        old_id = _assert_tuple(tmp_path, old, 42, 1)
    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    lifecycle.root.mkdir(parents=True, exist_ok=True)
    unknown = lifecycle.root / "unknown-user-file"
    unknown.write_text("preserve")
    previous = tmp_path / "health.duckdb.previous"
    previous.write_text("ambiguous legacy copy")

    _child(tmp_path, "import", new, boundary=boundary, expected=73)
    expected = new if boundary in COMMITTED else old if replacement else None
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(
            tmp_path, expected, 999 if expected == new else 42, 2 if expected == new else 1
        )
        assert unknown.read_text() == "preserve"
        assert previous.read_text() == "ambiguous legacy copy"
    if old_id:
        assert (lifecycle.root / "generations" / old_id / "health.duckdb").is_file()


@pytest.mark.parametrize("boundary", RECOVERY_BOUNDARIES)
def test_recovery_can_die_and_restart_twice(tmp_path, boundary):
    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new, boundary="pointer_committed", expected=73)
    _child(tmp_path, "recover", boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(tmp_path, new, 999, 2)


@pytest.mark.parametrize("replacement", [False, True])
def test_process_death_inside_sqlite_projection_transaction(tmp_path, replacement):
    old = _export(tmp_path, "old-root", 42, 1)
    new = _export(tmp_path, "new-root", 999, 2)
    if replacement:
        _child(tmp_path, "import", old)
    _child(tmp_path, "import", new, boundary="sqlite_transaction", expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(tmp_path, new, 999, 2)


@pytest.mark.parametrize("boundary", ["generation_fsynced", "pointer_committed"])
@pytest.mark.parametrize("kind", ["cancel", "sigkill"])
def test_cancellation_and_sigkill_obey_commit_point(tmp_path, boundary, kind):
    new = _export(tmp_path, "new-root", 999, 2)
    expected_code = -signal.SIGKILL if kind == "sigkill" else -signal.SIGINT
    _child(tmp_path, "import", new, boundary=boundary, kind=kind, expected=expected_code)
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(tmp_path, new if boundary == "pointer_committed" else None, 999, 2)


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_legacy_adoption_copies_original_and_never_guesses_previous(tmp_path, boundary):
    from app.db.dataset_lifecycle import DatasetLifecycle

    old = _export(tmp_path, "old-root", 42, 1)
    _child(tmp_path, "import", old, "--legacy")
    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    generation = lifecycle.active()
    assert generation is not None
    original = tmp_path / "health.duckdb"
    original.write_bytes(generation.database_path.read_bytes())
    # Recreate the pre-lifecycle installation without removing any real data.
    import shutil

    shutil.rmtree(lifecycle.root)
    original_bytes = original.read_bytes()
    _child(tmp_path, "startup", boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(tmp_path, old, 42, 1)
        assert original.read_bytes() == original_bytes


def test_uncommitted_generation_and_pointer_temp_are_not_activation(tmp_path):
    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new, boundary="pointer_fsynced", expected=73)
    _child(tmp_path, "recover")
    _assert_tuple(tmp_path, None, 0, 0)
    assert not (tmp_path / "health.duckdb").exists()


@pytest.mark.parametrize("replacement", [False, True])
def test_official_cli_recovers_before_resolving_managed_identity(tmp_path, replacement):
    from app.db.dataset_lifecycle import DatasetLifecycle

    old = _export(tmp_path, "old-root", 42, 1)
    new = _export(tmp_path, "new-root", 999, 2)
    if replacement:
        _child(tmp_path, "import", old)
    _child(tmp_path, "import", new, boundary="pointer_committed", expected=73)
    for _ in range(2):
        response = json.loads(_child(tmp_path, "cli").stdout)
        active = DatasetLifecycle(tmp_path / "health.duckdb").active()
        assert active is not None
        assert response["data"]["text"] == "999.0"
        assert response["metadata"]["dataset_version_id"] == active.dataset.id
        _assert_tuple(tmp_path, new, 999, 2)


def test_external_cli_does_not_recover_or_associate_with_managed_pointer(tmp_path):
    from app.db.dataset_lifecycle import DatasetLifecycle

    old = _export(tmp_path, "old-root", 42, 1)
    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", old)
    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    active = lifecycle.active()
    assert active is not None
    external = tmp_path / "external.duckdb"
    external.write_bytes(active.database_path.read_bytes())
    _child(tmp_path, "import", new, boundary="pointer_committed", expected=73)
    # Even an unavailable managed store must not stop independent external use.
    (lifecycle.root / "active.json").write_text("malformed managed pointer")
    response = json.loads(_child(tmp_path, "cli", "--db-path", external).stdout)
    assert response["data"]["text"] == "42.0"
    assert response["metadata"]["dataset_version_id"] is None
    assert AppStateRepository(tmp_path / "state.sqlite").get_active() == active.dataset


def test_managed_cli_recovery_error_is_safe_and_useful(tmp_path):
    from app.db.dataset_lifecycle import DatasetLifecycle

    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new)
    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    (lifecycle.root / "active.json").write_text("malformed pointer")
    command = [sys.executable, "-m", "app.cli.chat", "--question", "Show my last run", "--json"]
    result = subprocess.run(  # noqa: S603
        command,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert "Dataset recovery is required" in result.stderr
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr


def test_corrupt_pointer_fails_closed_preserving_all_candidates(tmp_path):
    from app.db.dataset_lifecycle import DatasetLifecycle

    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new)
    lifecycle = DatasetLifecycle(tmp_path / "health.duckdb")
    pointer = lifecycle.root / "active.json"
    pointer.write_text(json.dumps({"format_version": 100, "generation_id": "../escape"}))
    before = {
        p.relative_to(lifecycle.root): p.read_bytes()
        for p in lifecycle.root.rglob("*")
        if p.is_file()
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CHILD, "startup"],
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "Dataset recovery is required" in result.stderr
    assert before == {
        p.relative_to(lifecycle.root): p.read_bytes()
        for p in lifecycle.root.rglob("*")
        if p.is_file()
    }
