"""Synthetic ownership and OS-lock recovery regressions; no providers or user data."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.app_state import AppStateRepository
from app.state.import_artifacts import ImportOperation, recover_imports


def _environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    return DatasetLifecycle()


def test_dead_operation_cleanup_is_idempotent_and_preserves_unknowns(monkeypatch, tmp_path):
    lifecycle = _environment(monkeypatch, tmp_path)
    root = tmp_path / "shards"
    root.mkdir()
    sentinel = root / "sentinel.txt"
    sentinel.write_text("caller")
    legacy = tmp_path / "tti-import-legacy.duckdb"
    legacy.write_text("unproven")
    operation = ImportOperation.create(lifecycle)
    upload = operation.upload_path
    upload.write_text("<HealthData/>")
    shards = operation.new_directory("shards", root)
    (shards / "records-0000-0000.parquet").write_bytes(b"partial")
    staging = operation.new_directory("staging", lifecycle.root / "staging")
    (staging / "health.duckdb").write_bytes(b"partial")
    operation.close()
    for _ in range(3):
        recover_imports(lifecycle, AppStateRepository())
    assert not upload.exists()
    assert not shards.exists()
    assert not staging.exists()
    assert sentinel.read_text() == "caller"
    assert legacy.read_text() == "unproven"


def test_live_operation_and_detached_worker_prevent_cleanup(monkeypatch, tmp_path):
    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    attached = ImportOperation.attach(lifecycle, operation.id)
    operation.close()
    recover_imports(lifecycle, AppStateRepository())
    assert attached.upload_path.exists()
    attached.close()
    recover_imports(lifecycle, AppStateRepository())
    assert not attached.upload_path.exists()
    with pytest.raises((ValueError, OSError)):
        ImportOperation.attach(lifecycle, operation.id)


@pytest.mark.parametrize("damage", ["symlink", "inode", "malformed", "lock", "unknown", "gpx"])
def test_ambiguous_ownership_fails_closed(monkeypatch, tmp_path, damage):
    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    root = tmp_path / "shards"
    root.mkdir()
    shards = operation.new_directory("shards", root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "export.xml").write_text("caller export")
    if damage in {"symlink", "inode"}:
        shards.rename(root / "original")
        if damage == "symlink":
            shards.symlink_to(outside, target_is_directory=True)
        else:
            shards.mkdir()
            (shards / "sentinel.txt").write_text("replacement")
    elif damage == "malformed":
        operation.record_path.write_text('{"format_version":999}')
    elif damage == "lock":
        operation.lock_path.rename(operation.lock_path.with_suffix(".old"))
        operation.lock_path.touch()
    elif damage == "unknown":
        (shards / "sentinel.txt").write_text("unknown")
    else:
        (shards / "route.gpx").write_text("caller route")
    operation.close()
    recover_imports(lifecycle, AppStateRepository())
    assert shards.exists()
    assert (outside / "export.xml").read_text() == "caller export"


def test_recovery_reconciles_before_deleting(monkeypatch, tmp_path):
    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    operation.close()
    (lifecycle.root / "active.json").write_text("malformed")
    with pytest.raises(RuntimeError):
        recover_imports(lifecycle, AppStateRepository())
    assert operation.upload_path.exists()


@pytest.mark.parametrize("boundary", ["upload", "shards", "staging"])
def test_real_sigkill_recovers_only_owned_dead_artifacts(monkeypatch, tmp_path, boundary):
    lifecycle = _environment(monkeypatch, tmp_path)
    script = """
import os, signal, sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.import_artifacts import ImportOperation
op = ImportOperation.create(DatasetLifecycle())
op.upload_path.write_text('<HealthData/>')
if sys.argv[1] != 'upload':
    child = op.new_directory(sys.argv[1], DatasetLifecycle().root / sys.argv[1])
    name = 'health.duckdb' if sys.argv[1] == 'staging' else 'records-0000-0000.parquet'
    (child / name).write_bytes(b'partial')
print(op.id, flush=True)
os.kill(os.getpid(), signal.SIGKILL)
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, boundary], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == -signal.SIGKILL
    operation_id = result.stdout.strip()
    for _ in range(2):
        recover_imports(lifecycle, AppStateRepository())
    record = json.loads((lifecycle.root / "imports" / operation_id / "record.json").read_text())
    assert record["closed"] is True
    assert not (lifecycle.root / "imports" / operation_id / "upload.xml").exists()
    for artifact in record["artifacts"]:
        assert not Path(artifact["path"]).exists()


def test_published_generation_is_never_a_cleanup_candidate(monkeypatch, tmp_path):
    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    with pytest.raises(ValueError):
        operation.new_directory("staging", lifecycle.root / "generations")
    with pytest.raises(ValueError):
        operation.new_directory("shards", lifecycle.root / "generations")
    operation.close()


@pytest.mark.asyncio
async def test_restart_keeps_public_job_shape_and_honest_interrupted_state(monkeypatch, tmp_path):
    from app.api.imports import ImportJobManager
    from app.state.import_artifacts import JobRecord

    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    operation.save_job(
        JobRecord(
            id=operation.id,
            filename="export.xml",
            state="running",
            progress=0,
            created_at="2026-10-22T00:00:00+00:00",
            started_at="2026-10-22T00:00:01+00:00",
        )
    )
    operation.close()
    recover_imports(lifecycle, AppStateRepository())
    manager = ImportJobManager()
    job = manager.get(operation.id)
    assert job is not None
    assert job.state == "failed"
    assert job.progress == 0
    assert job.error == "The import was interrupted. Choose your export to try again."
    assert manager.list()[0] == job
    assert set(job.model_dump()) == {
        "id",
        "filename",
        "state",
        "progress",
        "report",
        "error",
        "created_at",
        "started_at",
        "completed_at",
    }
    assert str(tmp_path) not in job.model_dump_json()


@pytest.mark.asyncio
async def test_partial_upload_cancellation_is_owned_and_recovers(monkeypatch, tmp_path):
    import asyncio

    from app.api import imports

    lifecycle = _environment(monkeypatch, tmp_path)

    class Request:
        async def stream(self):
            yield b"<HealthData>"
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await imports._write_upload(Request(), "export.xml")
    recover_imports(lifecycle, AppStateRepository())
    assert not list((lifecycle.root / "imports").glob("*/upload.xml"))


def test_backend_sigkill_preserves_inherited_live_importer(monkeypatch, tmp_path):
    lifecycle = _environment(monkeypatch, tmp_path)
    script = r'''
import os, signal, subprocess, sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.import_artifacts import ImportOperation, JobRecord
op = ImportOperation.create(DatasetLifecycle())
op.save_job(JobRecord(id=op.id, filename='export.xml', state='running', progress=0,
                      created_at='2026-10-22T00:00:00+00:00'))
worker = """
import os, sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.import_artifacts import ImportOperation
op = ImportOperation.attach(DatasetLifecycle(), sys.argv[1])
print('ready', flush=True)
sys.stdin.readline()
op.close()
os.close(int(sys.argv[2]))
print('stopped', flush=True)
"""
process = subprocess.Popen([sys.executable, '-c', worker, op.id, str(op.fd)],
                           pass_fds=(op.fd,), stdin=sys.stdin)
print(op.id, flush=True)
os.kill(os.getpid(), signal.SIGKILL)
'''
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None and process.stdin is not None
        operation_id = process.stdout.readline().strip()
        assert process.stdout.readline().strip() == "ready"
        assert process.wait(timeout=20) == -signal.SIGKILL
        jobs = recover_imports(lifecycle, AppStateRepository())
        assert jobs[0].state == "running"
        upload = lifecycle.root / "imports" / operation_id / "upload.xml"
        assert upload.exists()
        process.stdin.write("stop\n")
        process.stdin.flush()
        assert process.stdout.readline().strip() == "stopped"
        jobs = recover_imports(lifecycle, AppStateRepository())
        assert jobs[0].state == "failed"
        assert not upload.exists()
    finally:
        process.communicate(timeout=20)


@pytest.mark.asyncio
async def test_timeout_has_terminal_safe_job_and_no_owned_orphans(monkeypatch, tmp_path):
    import asyncio

    from app.api import imports

    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    operation.upload_path.write_text("<HealthData/>")
    imports._UPLOAD_OPERATIONS[str(operation.upload_path)] = operation
    real_popen = subprocess.Popen

    def slow_import(command, **kwargs):
        del command
        return real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)

    monkeypatch.setattr(imports.subprocess, "Popen", slow_import)
    monkeypatch.setattr(imports, "IMPORT_TIMEOUT_SECONDS", 0.05)
    manager = imports.ImportJobManager()
    job = manager.start("export.xml", operation.upload_path)
    await asyncio.gather(*list(manager._tasks))
    result = manager.get(job.id)
    assert result is not None and result.state == "failed"
    assert result.progress == 0
    assert str(tmp_path) not in result.model_dump_json()
    assert not operation.upload_path.exists()
    assert not imports._IMPORT_PROCESSES


@pytest.mark.parametrize(
    "boundary,expected", [("staging_created", "failed"), ("pointer_committed", "succeeded")]
)
def test_importer_sigkill_reconciles_job_with_activation(monkeypatch, tmp_path, boundary, expected):
    from app.state.import_artifacts import JobRecord
    from tests.integration.test_dataset_crash_recovery import CHILD

    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
    operation.upload_path.write_bytes(fixture.read_bytes())
    operation.save_job(
        JobRecord(
            id=operation.id,
            filename="export.xml",
            state="running",
            progress=0,
            created_at="2026-10-22T00:00:00+00:00",
        )
    )
    environment = dict(
        os.environ,
        TTI_IMPORT_OPERATION=operation.id,
        TTI_IMPORT_OPERATION_FD=str(operation.fd),
        CRASH_BOUNDARY=boundary,
        FAULT_KIND="sigkill",
        TTI_INGEST_WORKERS="1",
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CHILD, "import", str(operation.upload_path)],
        env=environment,
        pass_fds=(operation.fd,),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == -signal.SIGKILL
    operation.close()
    previous = None
    for _ in range(2):
        jobs = recover_imports(lifecycle, AppStateRepository())
        if previous is not None:
            assert jobs[0] == previous
        previous = jobs[0]
        assert jobs[0].state == expected
        assert str(tmp_path) not in jobs[0].model_dump_json()
    assert not operation.upload_path.exists()
    assert not list((lifecycle.root / "staging").glob("*/health.duckdb"))
    if expected == "succeeded":
        active = lifecycle.active()
        assert active is not None and active.database_path.exists()
        assert active.dataset.counts["records"] == 40
        assert jobs[0].report == {"dataset_version_id": active.dataset.id}


def test_safe_persisted_report_filters_raw_output_and_paths(monkeypatch, tmp_path):
    from app.state.import_artifacts import JobRecord, load_jobs

    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    operation.save_job(
        JobRecord(
            id=operation.id,
            filename="export.xml",
            state="succeeded",
            progress=100,
            created_at="2026-10-22T00:00:00+00:00",
            report={
                "mode": "v2",
                "dataset_version_id": "ds_test",
                "counts": {"records": 40},
                "output": "raw subprocess output",
                "path": str(tmp_path),
                "warnings": [str(tmp_path)],
                "timing_seconds": {"total_time_seconds": 0.1},
            },
        )
    )
    job = load_jobs(lifecycle)[0]
    assert job.report == {
        "mode": "v2",
        "dataset_version_id": "ds_test",
        "counts": {"records": 40},
        "warnings": [],
        "timing_seconds": {"total_time_seconds": 0.1},
    }
    assert str(tmp_path) not in job.model_dump_json()
    operation.close()


def test_completed_job_retains_measured_report_after_restart(monkeypatch, tmp_path):
    from app.state.import_artifacts import JobRecord

    lifecycle = _environment(monkeypatch, tmp_path)
    operation = ImportOperation.create(lifecycle)
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
    operation.upload_path.write_bytes(fixture.read_bytes())
    environment = dict(
        os.environ,
        TTI_IMPORT_OPERATION=operation.id,
        TTI_IMPORT_OPERATION_FD=str(operation.fd),
        TTI_INGEST_WORKERS="1",
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.ingest.run", "--report-json", str(operation.upload_path)],
        env=environment,
        pass_fds=(operation.fd,),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    job = JobRecord(
        id=operation.id,
        filename="export.xml",
        state="succeeded",
        progress=100,
        created_at="2026-10-22T00:00:00+00:00",
        completed_at="2026-10-22T00:01:00+00:00",
        report=report,
    )
    operation.save_job(job)
    operation.close()
    for _ in range(2):
        recovered = recover_imports(lifecycle, AppStateRepository())[0]
        assert recovered == job
        assert recovered.report["counts"]["records"] == 40
