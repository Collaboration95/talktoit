"""Directory replacement must never transfer durable cleanup authority."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import shutil

import pytest

from app.db import connection
from app.db.dataset_lifecycle import DatasetBusyError, DatasetLifecycle
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import _child
from tests.integration.test_dataset_snapshots import exports
from tests.integration.test_safety_review_corrections import leave_pending_retirement


@pytest.fixture
def safety_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(tmp_path / "shards"))
    sources = exports(tmp_path)
    _child(tmp_path, "import", sources[0])
    return DatasetLifecycle(), AppStateRepository(), sources


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize(
    "seam",
    [
        "cleanup_started",
        "before_lease",
        "after_lease",
        "validated",
        "before_unlink",
        "after_manifest",
    ],
)
def test_replacement_never_inherits_retirement_authority(
    safety_dataset, tmp_path, monkeypatch, seam, empty
):
    lifecycle, repo, sources = safety_dataset
    old = leave_pending_retirement(lifecycle, tmp_path, sources)
    proof = (lifecycle.root / "retirement.json").read_bytes()
    identity = old.parent.stat()
    saved = tmp_path / "original"
    replacement = tmp_path / "replacement"
    if empty:
        replacement.mkdir()
    else:
        shutil.copytree(old.parent, replacement)
    expected = {p.name: p.read_bytes() for p in replacement.iterdir()}
    replacement_identity = replacement.stat()
    events = []
    unlinked = []
    real_unlink = os.unlink

    def unlink(path, *args, **kwargs):
        if path in {"health.duckdb", "manifest.json"}:
            unlinked.append((path, os.fstat(kwargs["dir_fd"]).st_ino))
        return real_unlink(path, *args, **kwargs)

    def swap():
        if not events:
            old.parent.rename(saved)
            replacement.rename(old.parent)
            events.append(seam)

    real_boundary = DatasetLifecycle._boundary
    real_lock = DatasetLifecycle._lock
    close = connection.close_open_connections

    def boundary(self, name):
        if seam == "cleanup_started" and name == "retirement_cleanup_started":
            swap()
        if seam == "validated" and name == "generation_directory_validated":
            swap()
        if seam == "after_manifest" and name == "generation_manifest_unlinked":
            swap()
        real_boundary(self, name)

    def lock(fd, operation, timeout):
        # The pending generation EX lease is taken after the lifecycle writer
        # lock. Identify its actual inode instead of counting flock calls.
        lease = lifecycle.root / "leases" / f"{old.parent.name}.lock"
        lease_stat = lease.stat()
        is_generation = os.fstat(fd).st_ino == lease_stat.st_ino
        if is_generation and operation == fcntl.LOCK_EX and seam == "before_lease":
            swap()
        real_lock(fd, operation, timeout)
        if is_generation and operation == fcntl.LOCK_EX and seam == "after_lease":
            swap()

    def before_close(path=None):
        # All directory/content validation has completed immediately before
        # idle-close and the first destructive file operation.
        if seam == "before_unlink" and path == old:
            swap()
        return close(path)

    monkeypatch.setattr(DatasetLifecycle, "_boundary", boundary)
    monkeypatch.setattr(DatasetLifecycle, "_lock", staticmethod(lock))
    monkeypatch.setattr(connection, "close_open_connections", before_close)
    monkeypatch.setattr(os, "unlink", unlink)
    for _ in range(3):
        assert lifecycle.recover(repo).export_root == sources[2].parent
        assert old.parent.is_dir()
        assert old.parent.stat().st_ino == replacement_identity.st_ino
        assert {p.name: p.read_bytes() for p in old.parent.iterdir()} == expected
        assert (lifecycle.root / "retirement.json").read_bytes() == proof
    assert events == [seam]
    assert saved.stat().st_ino == identity.st_ino
    assert all(inode == identity.st_ino for _, inode in unlinked)
    if seam in {"before_unlink", "after_manifest"}:
        assert [name for name, _ in unlinked] == ["health.duckdb", "manifest.json"]
    if seam not in {"before_unlink", "after_manifest"}:
        assert (saved / "health.duckdb").is_file()
    assert len(json.loads(proof)["generations"]) == 1


@pytest.mark.parametrize("seam", ["after_lease", "before_unlink", "after_manifest"])
@pytest.mark.parametrize("empty", [False, True])
def test_explicit_deletion_cannot_adopt_replacement_on_restart(
    safety_dataset, tmp_path, monkeypatch, seam, empty
):
    lifecycle, repo, _ = safety_dataset
    old = lifecycle.active().database_path
    replacement = tmp_path / "replacement"
    if empty:
        replacement.mkdir()
    else:
        shutil.copytree(old.parent, replacement)
    expected = {p.name: p.read_bytes() for p in replacement.iterdir()}
    saved = tmp_path / "original"
    events = []

    def swap():
        if not events:
            old.parent.rename(saved)
            replacement.rename(old.parent)
            events.append(seam)

    real_lock = DatasetLifecycle._lock
    close = connection.close_open_connections

    def lock(fd, operation, timeout):
        real_lock(fd, operation, timeout)
        lease = lifecycle.root / "leases" / f"{old.parent.name}.lock"
        if seam == "after_lease" and os.fstat(fd).st_ino == lease.stat().st_ino:
            swap()

    def before_close(path=None):
        if seam == "before_unlink" and path == old:
            swap()
        return close(path)

    def boundary(self, name):
        if seam == "after_manifest" and name == "generation_manifest_unlinked":
            swap()

    monkeypatch.setattr(DatasetLifecycle, "_lock", staticmethod(lock))
    monkeypatch.setattr(connection, "close_open_connections", before_close)
    monkeypatch.setattr(DatasetLifecycle, "_boundary", boundary)
    with pytest.raises(DatasetBusyError):
        lifecycle.delete(repo, timeout=0)
    proof = (lifecycle.root / "deletion.json").read_bytes()
    for _ in range(3):
        assert lifecycle.recover(repo) is None
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert old.parent.is_dir()
        assert {p.name: p.read_bytes() for p in old.parent.iterdir()} == expected
        assert (lifecycle.root / "deletion.json").read_bytes() == proof
    assert events == [seam]


@pytest.mark.parametrize("entry", ["manifest.json", "health.duckdb", "lease"])
@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_cleanup_rejects_nonregular_files_without_following_or_blocking(
    safety_dataset, tmp_path, entry, kind
):
    lifecycle, repo, sources = safety_dataset
    old = leave_pending_retirement(lifecycle, tmp_path, sources)
    proof = (lifecycle.root / "retirement.json").read_bytes()
    path = (
        lifecycle.root / "leases" / f"{old.parent.name}.lock"
        if entry == "lease"
        else old.with_name(entry)
    )
    saved = tmp_path / "preserved-file"
    path.rename(saved)
    expected = saved.read_bytes()
    if kind == "symlink":
        path.symlink_to(saved)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    for _ in range(2):
        assert lifecycle.recover(repo).export_root == sources[2].parent
        assert (lifecycle.root / "retirement.json").read_bytes() == proof
        assert saved.read_bytes() == expected
        assert path.is_symlink() if kind == "symlink" else path.exists()
    if entry != "health.duckdb":
        assert old.is_file()


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize(
    "seam",
    [
        "generation_directory_validated",
        "deletion_database_unlinked",
        "generation_directory_fsynced",
    ],
)
def test_cleanup_closes_every_descriptor_after_io_failure_or_cancellation(
    safety_dataset, tmp_path, monkeypatch, cancel, seam
):
    lifecycle, repo, sources = safety_dataset
    old = leave_pending_retirement(lifecycle, tmp_path, sources)
    proof = (lifecycle.root / "retirement.json").read_bytes()
    descriptors, events = [], []
    real_open = os.open

    def opened(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        descriptors.append(fd)
        return fd

    def fail(self, name):
        if name == seam and not events:
            events.append(name)
            if cancel:
                raise asyncio.CancelledError()
            raise OSError("synthetic cleanup error")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", opened)
        patch.setattr(DatasetLifecycle, "_boundary", fail)
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                lifecycle.recover(repo)
        else:
            lifecycle.recover(repo)
    assert events == [seam]
    assert (lifecycle.root / "retirement.json").read_bytes() == proof
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)
    for _ in range(2):
        lifecycle.recover(repo)
    assert not old.exists()
    assert json.loads((lifecycle.root / "retirement.json").read_bytes())["generations"] == []


def test_explicit_deletion_preserves_uncommitted_generation(safety_dataset, tmp_path):
    lifecycle, repo, sources = safety_dataset
    original = lifecycle.active().database_path
    _child(tmp_path, "import", sources[1], boundary="generation_fsynced", expected=73)
    unknown = next(p for p in (lifecycle.root / "generations").iterdir() if p != original.parent)
    expected = {p.name: p.read_bytes() for p in unknown.iterdir()}
    assert lifecycle.delete(repo) == 1
    for _ in range(2):
        assert lifecycle.recover(repo) is None
        assert lifecycle.delete(repo) == 0
        assert {p.name: p.read_bytes() for p in unknown.iterdir()} == expected
    assert not original.exists()


@pytest.mark.parametrize("fail_flush", [False, True])
def test_proof_pruning_requires_anchored_directory_and_parent_flush(
    safety_dataset, tmp_path, monkeypatch, fail_flush
):
    lifecycle, repo, sources = safety_dataset
    old = leave_pending_retirement(lifecycle, tmp_path, sources)
    proof = (lifecycle.root / "retirement.json").read_bytes()
    directory = old.parent.stat().st_ino
    parent = old.parent.parent.stat().st_ino
    flushed, pruned = [], []
    fsync = os.fsync

    def flush(fd):
        inode = os.fstat(fd).st_ino
        if inode == directory and fail_flush:
            raise OSError("synthetic directory flush failure")
        fsync(fd)
        flushed.append(inode)

    def boundary(self, name):
        if name == "retirement_drained_written":
            assert directory in flushed
            assert parent in flushed[flushed.index(directory) + 1 :]
            pruned.append(name)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", flush)
        patch.setattr(DatasetLifecycle, "_boundary", boundary)
        lifecycle.recover(repo)
    assert not old.exists()
    if fail_flush:
        assert not pruned
        assert (lifecycle.root / "retirement.json").read_bytes() == proof
    else:
        assert pruned == ["retirement_drained_written"]
    for _ in range(2):
        lifecycle.recover(repo)
    assert json.loads((lifecycle.root / "retirement.json").read_bytes())["generations"] == []


def test_old_deletion_intent_without_identity_cannot_claim_present_copy(safety_dataset):
    lifecycle, repo, _ = safety_dataset
    old = lifecycle.active().database_path
    # Simulate an interrupted pre-correction intent. There is no persisted inode
    # to validate, so neither startup nor retry can invent that missing proof.
    pointer = json.loads((lifecycle.root / "active.json").read_bytes())
    intent = lifecycle.root / "deletion.json"
    intent.write_text(json.dumps({"format_version": 1, "generations": [pointer], "legacy": False}))
    with pytest.raises(DatasetBusyError):
        lifecycle.delete(repo)
    for _ in range(2):
        assert lifecycle.recover(repo) is None
        assert old.is_file()
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo)
    old.unlink()  # Missing files remain idempotent, including old intent format.
    old.with_name("manifest.json").unlink()
    assert lifecycle.delete(repo) == 0
