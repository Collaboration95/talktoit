"""Validation, ordinary failures, and compatibility around durable publication."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace

import duckdb
import pytest

from app.db.connection import connect, resolve_effective_db_path
from app.db.dataset_lifecycle import DatasetLifecycle, DatasetRecoveryError
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import _assert_tuple, _child, _export


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    old = _export(tmp_path, "old-root", 42, 1)
    _child(tmp_path, "import", old)
    return DatasetLifecycle(), AppStateRepository(), old


@pytest.mark.parametrize("operation", ["fsync", "rename", "projection", "manifest", "commit_fsync"])
def test_ordinary_activation_failure_recovers_matching_generation(tmp_path, monkeypatch, operation):
    lifecycle, repo, old = _prepare(tmp_path, monkeypatch)
    new = _export(tmp_path, "new-root", 999, 2)
    # Build a second valid closed DB through the official importer first.
    other = tmp_path / "other"
    other.mkdir()
    other_export = _export(other, "new-root", 999, 2)
    _child(other, "import", other_export)
    source = DatasetLifecycle(other / "health.duckdb").active()
    assert source is not None

    with lifecycle.writer_lock():
        staging = lifecycle.new_staging()
        shutil.copyfile(source.database_path, staging)
        dataset = repo.build_file_manifest(
            new,
            parser_version="v2",
            schema_version="1",
            worker_count=1,
            coverage_start="2024-01-01",
            coverage_end="2024-01-01",
            counts=source.dataset.counts,
        )
        with monkeypatch.context() as patch:
            if operation == "fsync":
                patch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("flush")))
            elif operation == "rename":
                patch.setattr(os, "rename", lambda *a: (_ for _ in ()).throw(OSError("rename")))
            elif operation == "projection":
                patch.setattr(
                    repo, "project_generation", lambda *a: (_ for _ in ()).throw(OSError("SQLite"))
                )
            elif operation == "commit_fsync":
                import app.db.dataset_lifecycle as module

                real_fsync = module._fsync_directory

                def fail_after_replace(path):
                    current = lifecycle.active()
                    if path == lifecycle.root and current and current.dataset.id == dataset.id:
                        raise OSError("commit flush")
                    real_fsync(path)

                patch.setattr(module, "_fsync_directory", fail_after_replace)
            else:
                real_write = lifecycle._write

                def fail_manifest(path, record, phase):
                    if phase == "manifest":
                        raise OSError("manifest")
                    real_write(path, record, phase)

                patch.setattr(lifecycle, "_write", fail_manifest)
            with pytest.raises(OSError):
                lifecycle.activate(staging, dataset, new.parent, repo)
    for _ in range(2):
        lifecycle.recover(repo)
        _assert_tuple(
            tmp_path,
            new if operation in {"projection", "commit_fsync"} else old,
            999 if operation in {"projection", "commit_fsync"} else 42,
            2 if operation in {"projection", "commit_fsync"} else 1,
        )


def test_journal_proves_previous_generation_when_new_database_is_damaged(tmp_path, monkeypatch):
    lifecycle, repo, old = _prepare(tmp_path, monkeypatch)
    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new, boundary="pointer_replaced", expected=73)
    generation = lifecycle.active()
    assert generation is not None
    generation.database_path.write_bytes(b"broken new candidate")
    for _ in range(2):
        lifecycle.recover(repo)
        _assert_tuple(tmp_path, old, 42, 1)
        assert generation.database_path.read_bytes() == b"broken new candidate"


@pytest.mark.parametrize("artifact", ["root", "pointer", "manifest", "database", "lease"])
def test_symlinked_managed_artifacts_fail_closed(tmp_path, monkeypatch, artifact):
    lifecycle, repo, _ = _prepare(tmp_path, monkeypatch)
    active = lifecycle.active()
    assert active is not None
    paths = {
        "root": lifecycle.root,
        "pointer": lifecycle.root / "active.json",
        "manifest": active.database_path.parent / "manifest.json",
        "database": active.database_path,
        "lease": lifecycle.root / "leases" / f"{active.dataset.id}.lock",
    }
    path = paths[artifact]
    saved = path.with_name(path.name + ".saved")
    path.rename(saved)
    path.symlink_to(saved, target_is_directory=saved.is_dir())
    with pytest.raises(DatasetRecoveryError):
        lifecycle.recover(repo)
    assert saved.exists()
    assert path.is_symlink()


@pytest.mark.parametrize("mutation", ["digest", "version", "extra", "traversal", "duplicate"])
def test_pointer_validation_preserves_last_good_data(tmp_path, monkeypatch, mutation):
    lifecycle, repo, _ = _prepare(tmp_path, monkeypatch)
    active = lifecycle.active()
    assert active is not None
    pointer = lifecycle.root / "active.json"
    data = json.loads(pointer.read_text())
    if mutation == "duplicate":
        pointer.write_text('{"format_version":1,' + pointer.read_text()[1:])
    else:
        key, value = {
            "digest": ("manifest_sha256", "0" * 64),
            "version": ("format_version", 2),
            "extra": ("unexpected", True),
            "traversal": ("generation_id", "../../outside"),
        }[mutation]
        data[key] = value
        pointer.write_text(json.dumps(data))
    with pytest.raises(DatasetRecoveryError):
        lifecycle.recover(repo)
    assert active.database_path.exists()


def test_tombstone_never_resurrects_legacy_data(tmp_path, monkeypatch):
    lifecycle, repo, _ = _prepare(tmp_path, monkeypatch)
    active = lifecycle.active()
    assert active is not None
    lifecycle.target.write_bytes(active.database_path.read_bytes())
    (lifecycle.root / "active.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "generation_id": None,
                "manifest_sha256": None,
            }
        )
    )
    for _ in range(2):
        assert lifecycle.recover(repo) is None
        assert repo.get_active() is None
        assert repo.get_export_root() is None
        with pytest.raises(DatasetRecoveryError):
            connect()
    assert lifecycle.target.exists()
    assert active.database_path.exists()


@pytest.mark.parametrize("missing", ["database", "manifest", "root", "counts", "coverage"])
def test_legacy_adoption_requires_proven_matching_tuple(tmp_path, monkeypatch, missing):
    lifecycle, repo, _ = _prepare(tmp_path, monkeypatch)
    active = lifecycle.active()
    assert active is not None
    lifecycle.target.write_bytes(active.database_path.read_bytes())
    shutil.rmtree(lifecycle.root)
    if missing == "database":
        lifecycle.target.unlink()
    elif missing == "manifest":
        repo.deactivate_active_dataset()
    elif missing == "root":
        with repo._connection() as conn:
            conn.execute("DELETE FROM app_state WHERE key = 'export_root'")
    elif missing == "coverage":
        repo.project_generation(
            replace(active.dataset, coverage_start="2023-01-01"), active.export_root
        )
    else:
        repo.project_generation(replace(active.dataset, counts={"records": 55}), active.export_root)
    original = lifecycle.target.read_bytes() if lifecycle.target.exists() else None
    with pytest.raises(DatasetRecoveryError):
        lifecycle.recover(repo)
    assert not (lifecycle.root / "active.json").exists()
    assert (lifecycle.target.read_bytes() if lifecycle.target.exists() else None) == original


@pytest.mark.parametrize(
    "boundary",
    [
        "restore_written",
        "restore_fsynced",
        "recovery_validated",
        "recovery_pointer_fsynced",
        "recovery_projected",
    ],
)
def test_restoring_last_good_pointer_can_be_interrupted(tmp_path, monkeypatch, boundary):
    lifecycle, _, old = _prepare(tmp_path, monkeypatch)
    new = _export(tmp_path, "new-root", 999, 2)
    _child(tmp_path, "import", new, boundary="pointer_replaced", expected=73)
    damaged = lifecycle.active()
    assert damaged is not None
    damaged.database_path.write_bytes(b"damaged candidate, preserve")
    _child(tmp_path, "recover", boundary=boundary, expected=73)
    for _ in range(2):
        _child(tmp_path, "startup")
        _assert_tuple(tmp_path, old, 42, 1)
        assert damaged.database_path.read_bytes() == b"damaged candidate, preserve"


def test_effective_path_uses_immutable_generation_and_keeps_override_isolated(
    tmp_path, monkeypatch
):
    lifecycle, _, _ = _prepare(tmp_path, monkeypatch)
    active = lifecycle.active()
    assert active is not None
    assert resolve_effective_db_path() == active.database_path
    assert resolve_effective_db_path(lifecycle.target) == active.database_path
    with connect() as conn:
        assert conn.execute("SELECT value FROM records").fetchone() == (42,)
        with pytest.raises(duckdb.Error):
            conn.execute("DELETE FROM records")
    other = tmp_path / "explicit.duckdb"
    assert resolve_effective_db_path(other) == other
    with connect(other) as conn:
        conn.execute("CREATE TABLE isolated(value INTEGER)")
