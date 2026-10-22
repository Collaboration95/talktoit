"""Capture source races, durable claim replay and bounded private-namespace trust."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from app.db.dataset_lifecycle import DatasetBusyError, DatasetLifecycle
from app.state import cleanup_claims as claims
from app.state.app_state import AppStateRepository
from app.state.import_artifacts import ImportOperation, recover_imports
from tests.integration import test_retirement_ownership as ownership
from tests.integration.test_dataset_crash_recovery import _child
from tests.integration.test_legacy_deletion_authority import write_old_intent
from tests.integration.test_safety_review_corrections import leave_pending_retirement


@pytest.fixture
def safety_dataset(tmp_path, monkeypatch):
    return ownership.safety_dataset.__wrapped__(tmp_path, monkeypatch)


def records(root):
    return [json.loads(p.read_bytes()) for p in (root / "cleanup-claims").glob("*/record.json")]


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("entry", ["health.duckdb", "manifest.json"])
@pytest.mark.parametrize("identical", [False, True])
@pytest.mark.parametrize("seam", ["before_capture", "after_capture", "at_private_unlink"])
def test_generation_source_replacement_never_reaches_disposal(
    safety_dataset, tmp_path, monkeypatch, explicit, entry, identical, seam
):
    lifecycle, repo, sources = safety_dataset
    old = (
        lifecycle.active().database_path
        if explicit
        else leave_pending_retirement(lifecycle, tmp_path, sources)
    )
    source = old.with_name(entry)
    value = source.stat()
    marker = source.read_bytes() if identical else b"UNOWNED child replacement"
    original = tmp_path / "original-file"
    proof = lifecycle.root / ("deletion.json" if explicit else "retirement.json")
    events, before = [], []
    rename, unlink = os.rename, os.unlink

    def swap(before_capture):
        if events:
            return
        before.append(proof.read_bytes())
        if before_capture:
            source.rename(original)
        source.write_bytes(marker)
        assert source.stat().st_ino != value.st_ino
        events.append(seam)

    def capture(src, dst, *args, **kwargs):
        match = src == entry and dst == "payload" and kwargs.get("src_dir_fd") is not None
        if match and seam == "before_capture":
            swap(True)
        result = rename(src, dst, *args, **kwargs)
        if match and seam == "after_capture":
            swap(False)
        return result

    def dispose(path, *args, **kwargs):
        assert path not in {"health.duckdb", "manifest.json"}
        if path == "payload" and seam == "at_private_unlink":
            captured = os.stat(path, dir_fd=kwargs["dir_fd"], follow_symlinks=False)
            if captured.st_ino == value.st_ino:
                swap(False)
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "rename", capture)
    monkeypatch.setattr(os, "unlink", dispose)
    for _ in range(3):
        if explicit:
            with pytest.raises(DatasetBusyError):
                lifecycle.delete(repo, timeout=0)
            assert lifecycle.active() is None
        else:
            assert lifecycle.recover(repo).export_root == sources[2].parent
        assert source.read_bytes() == marker
        assert proof.read_bytes() == before[0]
    assert events == [seam]
    if seam == "before_capture":
        assert original.is_file()
        quarantined = [r for r in records(lifecycle.root) if r["state"] == "QUARANTINED"]
        assert len(quarantined) == 1
        assert (Path(quarantined[0]["namespace"]) / "payload").read_bytes() == marker
    else:
        completed = [
            r
            for r in records(lifecycle.root)
            if r["source_name"] == entry and r["state"] == "CLEANED"
        ]
        assert len(completed) == 1  # This tombstone prevents same-byte recapture.
        assert completed[0]["expected"] == [value.st_dev, value.st_ino]


@pytest.mark.parametrize("identical", [False, True])
@pytest.mark.parametrize("seam", ["before_capture", "after_capture", "before_disposal"])
def test_artifact_capture_preserves_replacement_directory_and_parent(
    tmp_path, monkeypatch, identical, seam
):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    lifecycle = DatasetLifecycle()
    operation = ImportOperation.create(lifecycle)
    parent = tmp_path / "external-configured-root"
    child = operation.new_directory("shards", parent)
    (parent / "parent-sentinel").write_bytes(b"keep parent")
    (child / "records-0000-0000.parquet").write_bytes(b"owned synthetic shard")
    original_inode = child.stat().st_ino
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    name = "records-0000-0000.parquet" if identical else "caller-sentinel"
    marker = b"owned synthetic shard" if identical else b"foreign directory sentinel"
    (replacement / name).write_bytes(marker)
    original = tmp_path / "original-allocation"
    operation.close()
    events = []
    rename = os.rename

    def swap(before):
        if events:
            return
        if before:
            child.rename(original)
        replacement.rename(child)
        events.append(seam)

    def capture(src, dst, *args, **kwargs):
        match = src == child.name and dst == "payload"
        if match and seam == "before_capture":
            swap(True)
        result = rename(src, dst, *args, **kwargs)
        if match and seam == "after_capture":
            swap(False)
        return result

    def boundary(name):
        if name == "claim_disposal_started" and seam == "before_disposal":
            if any(
                r["source_name"] == child.name and r["state"] == "VALIDATED"
                for r in records(lifecycle.root)
            ):
                swap(False)

    monkeypatch.setattr(os, "rename", capture)
    monkeypatch.setattr(claims, "claim_boundary", boundary)
    for _ in range(3):
        recover_imports(lifecycle, AppStateRepository())
        assert (parent / "parent-sentinel").read_bytes() == b"keep parent"
        item = next(r for r in records(lifecycle.root) if r["source_name"] == child.name)
        assert item["expected"][1] == original_inode
        preserved = Path(item["namespace"]) / "payload" if seam == "before_capture" else child
        assert (preserved / name).read_bytes() == marker
        assert Path(item["namespace"]).parent == parent  # Same filesystem, not the DB store.
    assert events == [seam]
    if seam == "before_capture":
        assert (original / "records-0000-0000.parquet").is_file()
        assert item["state"] == "QUARANTINED"


CLAIM_CHILD = """
import json, os, sys
from pathlib import Path
from app.state import cleanup_claims as c
root = Path(sys.argv[1])
spec = json.loads((root / 'original-authority.json').read_bytes())
def stop(name):
    if name == sys.argv[2]: os._exit(73)
with c.directory(root / 'source') as parent, c.directory(root) as namespace:
    result = c.remove_entry(root, authority=c.authority_key('original authority'),
        source_parent=root/'source', source_fd=parent, name='owned',
        namespace_parent=root, namespace_fd=namespace, policy=spec['policy'],
        expected=tuple(spec['identity']), digest=spec['digest'], boundary=stop)
    assert result is True
"""


def setup_claim(tmp_path, kind):
    parent = tmp_path / "source"
    parent.mkdir()
    source = parent / "owned"
    if kind == "directory":
        source.mkdir()
        (source / "records-0000-0000.parquet").write_bytes(b"original")
        policy, digest = "shards", None
    else:
        source.write_bytes(b"original")
        policy, digest = "generation_file", hashlib.sha256(b"original").hexdigest()
    value = source.stat()
    (tmp_path / "original-authority.json").write_text(
        json.dumps(
            {
                "policy": policy,
                "digest": digest,
                "identity": [value.st_dev, value.st_ino],
            }
        )
    )
    return source


def run_claim(tmp_path, boundary="", expected=0):
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", CLAIM_CHILD, str(tmp_path), boundary],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr


def remove_claim(tmp_path, boundary=None):
    spec = json.loads((tmp_path / "original-authority.json").read_bytes())
    with claims.directory(tmp_path / "source") as parent, claims.directory(tmp_path) as namespace:
        return claims.remove_entry(
            tmp_path,
            authority=claims.authority_key("original authority"),
            source_parent=tmp_path / "source",
            source_fd=parent,
            name="owned",
            namespace_parent=tmp_path,
            namespace_fd=namespace,
            policy=spec["policy"],
            expected=tuple(spec["identity"]),
            digest=spec["digest"],
            boundary=boundary,
        )


@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize(
    "phase",
    [
        "claim_prepared_committed",
        "claim_capture_started",
        "claim_captured",
        "claim_capture_parents_fsynced",
        "claim_captured_written",
        "claim_captured_fsynced",
        "claim_captured_committed",
        "claim_validated_written",
        "claim_validated_fsynced",
        "claim_validated_committed",
        "claim_disposal_started",
        "claim_disposed",
        "claim_cleaned_written",
        "claim_cleaned_fsynced",
        "claim_cleaned_committed",
    ],
)
def test_claim_process_death_replays_original_authority_without_refresh(tmp_path, kind, phase):
    source = setup_claim(tmp_path, kind)
    point = (
        ("claim_file_unlinked" if kind == "file" else "claim_child_unlinked")
        if phase == "claim_disposed"
        else phase
    )
    run_claim(tmp_path, point, expected=73)
    before = next(iter(records(tmp_path)))
    for _ in range(2):
        run_claim(tmp_path)
        assert not source.exists()
        after = next(iter(records(tmp_path)))
        assert after["expected"] == before["expected"]
        assert after["state"] == "CLEANED"
    if kind == "directory":
        assert list((Path(after["namespace"]) / "payload").iterdir()) == []
    else:
        assert not (Path(after["namespace"]) / "payload").exists()


@pytest.mark.parametrize("kind", ["file", "directory"])
@pytest.mark.parametrize("phase", ["claim_prepared_written", "claim_prepared_fsynced"])
def test_uncommitted_preparation_preserves_source_without_adopting_metadata(tmp_path, kind, phase):
    source = setup_claim(tmp_path, kind)
    original = source.stat().st_ino
    run_claim(tmp_path, phase, expected=73)
    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            remove_claim(tmp_path)
        assert source.stat().st_ino == original
        assert not records(tmp_path)
    # Only empty unproven claim namespace/metadata can precede PREPARED commit.
    assert all(not list(p.iterdir()) for p in tmp_path.glob(".tti_claim_*"))


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize(
    "phase",
    ["claim_capture_started", "claim_captured", "claim_disposal_started", "claim_file_unlinked"],
)
def test_claim_io_failure_or_cancellation_closes_fds_and_retries_without_new_authority(
    tmp_path, monkeypatch, cancel, phase
):
    source = setup_claim(tmp_path, "file")
    original = source.stat().st_ino
    opened, events = [], []
    real_open = os.open

    def track(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail(name):
        if name == phase:
            events.append(name)
            if cancel:
                raise asyncio.CancelledError()
            raise OSError("synthetic claim IO failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", track)
        with pytest.raises(asyncio.CancelledError if cancel else OSError):
            remove_claim(tmp_path, fail)
    assert events == [phase]
    assert records(tmp_path)[0]["expected"][1] == original
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
    for _ in range(2):
        assert remove_claim(tmp_path) is True
        assert records(tmp_path)[0]["expected"][1] == original


@pytest.mark.parametrize("operation", ["rename", "fsync"])
def test_real_capture_io_failures_remain_replayable(tmp_path, monkeypatch, operation):
    source = setup_claim(tmp_path, "file")
    parent_inode = source.parent.stat().st_ino
    original = source.stat().st_ino
    events = []
    real = getattr(os, operation)

    def fail(*args, **kwargs):
        match = (
            args[1] == "payload"
            if operation == "rename"
            else os.fstat(args[0]).st_ino == parent_inode
        )
        if match and not events:
            events.append(operation)
            raise OSError("synthetic unsupported rename or directory flush")
        return real(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, operation, fail)
        with pytest.raises(OSError):
            remove_claim(tmp_path)
    assert events == [operation]
    assert records(tmp_path)[0]["expected"][1] == original
    assert remove_claim(tmp_path) is True


@pytest.mark.parametrize("replacement", ["symlink", "fifo", "directory"])
def test_captured_special_files_are_never_opened_followed_or_deleted(tmp_path, replacement):
    source = setup_claim(tmp_path, "file")
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve target")

    def swap(name):
        if name == "claim_capture_started":
            source.rename(tmp_path / "original")
            if replacement == "symlink":
                source.symlink_to(outside)
            elif replacement == "fifo":
                os.mkfifo(source)
            else:
                source.mkdir()
                (source / "sentinel").write_bytes(b"keep directory")

    assert remove_claim(tmp_path, swap) is False
    record = records(tmp_path)[0]
    assert record["state"] == "QUARANTINED"
    payload = Path(record["namespace"]) / "payload"
    assert payload.is_symlink() if replacement == "symlink" else payload.exists()
    assert outside.read_bytes() == b"preserve target"
    assert (tmp_path / "original").read_bytes() == b"original"
    assert remove_claim(tmp_path) is False


@pytest.mark.parametrize("restore", ["occupied", "unsupported"])
def test_mismatch_restore_never_overwrites_or_discards_quarantine(tmp_path, monkeypatch, restore):
    source = setup_claim(tmp_path, "file")
    original = source.stat().st_ino
    rename = os.rename

    def capture(src, dst, *args, **kwargs):
        if src == "owned" and dst == "payload":
            source.rename(tmp_path / "original")
            source.write_bytes(b"foreign captured")
            result = rename(src, dst, *args, **kwargs)
            if restore == "occupied":
                source.write_bytes(b"second foreign source")
            return result
        return rename(src, dst, *args, **kwargs)

    def no_link(*args, **kwargs):
        raise OSError("synthetic link unsupported")

    monkeypatch.setattr(os, "rename", capture)
    if restore == "unsupported":
        monkeypatch.setattr(os, "link", no_link)
    assert remove_claim(tmp_path) is False
    record = records(tmp_path)[0]
    assert record["expected"][1] == original
    assert (Path(record["namespace"]) / "payload").read_bytes() == b"foreign captured"
    if restore == "occupied":
        assert source.read_bytes() == b"second foreign source"
    else:
        assert not source.exists()


def test_unexpected_private_destination_is_not_overwritten(tmp_path):
    source = setup_claim(tmp_path, "file")

    def occupy(name):
        if name == "claim_capture_started":
            record = records(tmp_path)[0]
            (Path(record["namespace"]) / "payload").write_bytes(b"unexpected payload")

    with pytest.raises(claims.ClaimError):
        remove_claim(tmp_path, occupy)
    assert source.read_bytes() == b"original"
    assert remove_claim(tmp_path) is False
    assert source.read_bytes() == b"original"
    record = records(tmp_path)[0]
    assert (Path(record["namespace"]) / "payload").read_bytes() == b"unexpected payload"


@pytest.mark.parametrize("damage", ["unknown", "duplicate", "oversize", "symlink"])
def test_claim_record_corruption_preserves_source_and_captured_bytes(tmp_path, damage):
    source = setup_claim(tmp_path, "file")
    run_claim(tmp_path, "claim_prepared_committed", expected=73)
    record_path = next((tmp_path / "cleanup-claims").glob("*/record.json"))
    original = record_path.read_bytes()
    if damage == "unknown":
        record_path.write_text('{"format_version":999}')
    elif damage == "duplicate":
        record_path.write_bytes(original[:-1] + b',"state":"CLEANED"}')
    elif damage == "oversize":
        record_path.write_bytes(b" " * (1024 * 1024 + 1))
    else:
        record_path.rename(record_path.with_name("original.json"))
        record_path.symlink_to(record_path.with_name("original.json"))
    for _ in range(2):
        with pytest.raises((ValueError, OSError, claims.ClaimError)):
            remove_claim(tmp_path)
        assert source.read_bytes() == b"original"


@pytest.mark.parametrize("entry", ["health.duckdb", "manifest.json"])
@pytest.mark.parametrize(
    "phase",
    [
        "claim_captured",
        "claim_validated_committed",
        "claim_file_unlinked",
        "claim_cleaned_committed",
    ],
)
def test_real_lifecycle_startup_replays_each_file_claim_before_pruning(
    safety_dataset, tmp_path, entry, phase
):
    lifecycle, repo, sources = safety_dataset
    old = leave_pending_retirement(lifecycle, tmp_path, sources)
    proof = (lifecycle.root / "retirement.json").read_bytes()
    code = """
import json, os, sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.app_state import AppStateRepository
lifecycle = DatasetLifecycle()
def boundary(self, name):
    if name == sys.argv[3]:
        for path in (self.root / 'cleanup-claims').glob('*/record.json'):
            record = json.loads(path.read_bytes())
            if record['source_parent'] == sys.argv[1] and record['source_name'] == sys.argv[2]:
                os._exit(73)
DatasetLifecycle._boundary = boundary
lifecycle.recover(AppStateRepository())
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, str(old.parent), entry, phase],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    assert (lifecycle.root / "retirement.json").read_bytes() == proof
    before = [r for r in records(lifecycle.root) if r["source_parent"] == str(old.parent)]
    for _ in range(2):
        _child(tmp_path, "startup")
        assert lifecycle.recover(repo).export_root == sources[2].parent
        assert not old.exists()
        assert json.loads((lifecycle.root / "retirement.json").read_bytes())["generations"] == []
    after = [r for r in records(lifecycle.root) if r["source_parent"] == str(old.parent)]
    for record in before:
        matching = next(item for item in after if item["source_name"] == record["source_name"])
        assert matching["expected"] == record["expected"]
        assert matching["state"] == "CLEANED"


@pytest.mark.parametrize(
    "phase",
    [
        "claim_captured",
        "claim_validated_committed",
        "claim_child_unlinked",
        "claim_cleaned_committed",
    ],
)
def test_real_artifact_recovery_replays_external_allocation_claim(tmp_path, monkeypatch, phase):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    lifecycle = DatasetLifecycle()
    operation = ImportOperation.create(lifecycle)
    parent = tmp_path / "external-root"
    child = operation.new_directory("shards", parent)
    (child / "records-0000-0000.parquet").write_bytes(b"synthetic shard")
    (parent / "caller-sentinel").write_bytes(b"preserved")
    original = child.stat()
    operation.close()
    code = """
import json, os, sys
from app.db.dataset_lifecycle import DatasetLifecycle
from app.state import cleanup_claims
from app.state.import_artifacts import recover_imports
lifecycle = DatasetLifecycle()
def stop(name):
    if name == sys.argv[2]:
        for path in (lifecycle.root / 'cleanup-claims').glob('*/record.json'):
            record = json.loads(path.read_bytes())
            if record['source_name'] == sys.argv[1]: os._exit(73)
cleanup_claims.claim_boundary = stop
recover_imports(lifecycle)
"""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, child.name, phase],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    record_path = operation.record_path
    before = record_path.read_bytes()
    for _ in range(3):
        recover_imports(lifecycle)
        assert record_path.read_bytes() == before
        assert not child.exists()
        assert (parent / "caller-sentinel").read_bytes() == b"preserved"
    claim = next(r for r in records(lifecycle.root) if r["source_name"] == child.name)
    assert claim["state"] == "CLEANED"
    assert claim["expected"] == [original.st_dev, original.st_ino]
    assert list((Path(claim["namespace"]) / "payload").iterdir()) == []


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("entry", ["health.duckdb", "manifest.json"])
def test_observed_source_replacement_after_claim_completion_keeps_authority(
    safety_dataset, tmp_path, monkeypatch, explicit, entry
):
    lifecycle, repo, sources = safety_dataset
    old = (
        lifecycle.active().database_path
        if explicit
        else leave_pending_retirement(lifecycle, tmp_path, sources)
    )
    proof = lifecycle.root / ("deletion.json" if explicit else "retirement.json")
    events, before = [], []
    phase = (
        "deletion_database_unlinked" if entry == "health.duckdb" else "generation_manifest_unlinked"
    )

    def replace(self, name):
        if name == phase and not events:
            before.append(proof.read_bytes())
            old.with_name(entry).write_bytes(b"foreign entry after completed claim")
            events.append(name)

    monkeypatch.setattr(DatasetLifecycle, "_boundary", replace)
    for _ in range(3):
        if explicit:
            with pytest.raises(DatasetBusyError):
                lifecycle.delete(repo, timeout=0)
        else:
            lifecycle.recover(repo)
        assert proof.read_bytes() == before[0]
        assert old.with_name(entry).read_bytes() == b"foreign entry after completed claim"
    assert events == [phase]


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_inconsistent_cleaned_payload_is_preserved_without_acknowledging_completion(tmp_path, kind):
    setup_claim(tmp_path, kind)
    assert remove_claim(tmp_path) is True
    record = records(tmp_path)[0]
    payload = Path(record["namespace"]) / "payload"
    # Corrupt persisted-state fixtures are not a claim to resist concurrent
    # arbitrary writers inside the trusted private namespace.
    if kind == "directory":
        payload = payload / "records-0000-0000.parquet"
    payload.write_bytes(b"unexpected remaining private object")
    for _ in range(2):
        assert remove_claim(tmp_path) is False
        assert payload.read_bytes() == b"unexpected remaining private object"
        assert records(tmp_path)[0] == record


@pytest.mark.parametrize("kind", ["upload", "shards"])
@pytest.mark.parametrize("cancel", [False, True])
def test_artifact_guard_and_claim_descriptors_close_after_error_or_cancel(
    tmp_path, monkeypatch, kind, cancel
):
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    lifecycle = DatasetLifecycle()
    operation = ImportOperation.create(lifecycle)
    if kind == "upload":
        source = operation.upload_path
        source.write_bytes(b"<HealthData/>")
    else:
        source = operation.new_directory("shards", tmp_path / "shards")
        (source / "records-0000-0000.parquet").write_bytes(b"synthetic")
    expected = source.stat()
    operation.close()
    opened, events = [], []
    real_open = os.open

    def track(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def fail(name):
        if name == "claim_captured" and not events:
            if any(r["source_name"] == source.name for r in records(lifecycle.root)):
                events.append(name)
                if cancel:
                    raise asyncio.CancelledError()
                raise OSError("synthetic captured artifact failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", track)
        patch.setattr(claims, "claim_boundary", fail)
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                recover_imports(lifecycle)
        else:
            recover_imports(lifecycle)
    assert events == ["claim_captured"]
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
    for _ in range(2):
        recover_imports(lifecycle)
    claim = next(r for r in records(lifecycle.root) if r["source_name"] == source.name)
    assert claim["expected"] == [expected.st_dev, expected.st_ino]
    assert claim["state"] == "CLEANED"
    assert not source.exists()


def test_missing_validated_directory_is_ambiguous_not_completed(tmp_path):
    setup_claim(tmp_path, "directory")
    run_claim(tmp_path, "claim_validated_committed", expected=73)
    record = records(tmp_path)[0]
    preserved = tmp_path / "uncertain-captured-allocation"
    (Path(record["namespace"]) / "payload").rename(preserved)
    assert remove_claim(tmp_path) is False
    assert (preserved / "records-0000-0000.parquet").read_bytes() == b"original"
    assert records(tmp_path)[0]["state"] == "QUARANTINED"


def legacy_source(tmp_path, monkeypatch):
    from app.db.schema import reset_schema

    source = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(source))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    with duckdb.connect(str(source)) as conn:
        reset_schema(conn)
    return source, DatasetLifecycle(), AppStateRepository()


@pytest.mark.parametrize("identical", [False, True])
def test_legacy_configured_database_replacement_cannot_reach_unlink(
    tmp_path, monkeypatch, identical
):
    source, lifecycle, repo = legacy_source(tmp_path, monkeypatch)
    original = tmp_path / "original-legacy"
    marker = source.read_bytes() if identical else b"unowned configured-source replacement"
    rename, unlink = os.rename, Path.unlink
    events, proof = [], []

    def swap():
        if not events:
            proof.append((lifecycle.root / "deletion.json").read_bytes())
            source.rename(original)
            source.write_bytes(marker)
            events.append("replacement")

    def old_unlink(path, *args, **kwargs):
        if path == source:
            swap()
        return unlink(path, *args, **kwargs)

    def capture(src, dst, *args, **kwargs):
        if src == source.name and dst == "payload":
            swap()
        return rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", old_unlink)
    monkeypatch.setattr(os, "rename", capture)
    for _ in range(3):
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert lifecycle.recover(repo) is None
        assert source.read_bytes() == marker
        assert (lifecycle.root / "deletion.json").read_bytes() == proof[0]
    assert events == ["replacement"]
    assert original.is_file()


def test_real_old_legacy_flag_cannot_manufacture_file_identity(tmp_path, monkeypatch):
    source, lifecycle, repo = legacy_source(tmp_path, monkeypatch)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    write_old_intent(tmp_path)
    for _ in range(3):
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert lifecycle.recover(repo) is None
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        assert (
            json.loads((lifecycle.root / "deletion.json").read_bytes()).get("legacy_identity")
            is None
        )
    source.unlink()  # Missing remains idempotent without creating authority.
    assert lifecycle.delete(repo, timeout=0) == 0


def test_new_proven_legacy_database_is_reclaimed_via_private_claim(tmp_path, monkeypatch):
    source, lifecycle, repo = legacy_source(tmp_path, monkeypatch)
    assert lifecycle.delete(repo) == 1
    assert not source.exists()
    assert lifecycle.active() is None
    assert lifecycle.recover(repo) is None
    assert lifecycle.delete(repo) == 0


def test_replay_cannot_consume_file_claim_that_lost_original_digest(tmp_path):
    setup_claim(tmp_path, "file")
    run_claim(tmp_path, "claim_captured_committed", expected=73)
    record_path = next((tmp_path / "cleanup-claims").glob("*/record.json"))
    record = json.loads(record_path.read_bytes())
    record["digest"] = None
    record_path.write_text(json.dumps(record))
    with claims.directory(tmp_path / "source") as parent, claims.directory(tmp_path) as namespace:
        with pytest.raises((ValueError, claims.ClaimError)):
            claims.remove_entry(
                tmp_path,
                authority=claims.authority_key("original authority"),
                source_parent=tmp_path / "source",
                source_fd=parent,
                name="owned",
                namespace_parent=tmp_path,
                namespace_fd=namespace,
                policy="generation_file",
            )
    assert (Path(record["namespace"]) / "payload").read_bytes() == b"original"
