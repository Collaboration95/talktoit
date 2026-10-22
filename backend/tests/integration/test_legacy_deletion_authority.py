"""Missing original deletion authority cannot be supplied by retirement replay."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import FunctionType

import pytest

from app.db import dataset_lifecycle as lifecycle_module
from app.db.dataset_lifecycle import DatasetBusyError, DatasetLifecycle
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import CHILD, _child, _env
from tests.integration.test_dataset_snapshots import exports

LEGACY = Path(__file__).resolve().parents[1] / "fixtures/lifecycle/dataset_lifecycle_5c21941.py.txt"
LEGACY_CHILD = """
import importlib.machinery, importlib.util, os, sys
from app.state.app_state import AppStateRepository
loader = importlib.machinery.SourceFileLoader('legacy_lifecycle', sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
loader.exec_module(module)
def boundary(self, name):
    if name == 'deletion_intent_committed':
        os._exit(73)
module.DatasetLifecycle._boundary = boundary
module.DatasetLifecycle().delete(AppStateRepository(), timeout=0)
"""


def contents(path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}


def queue_bytes(lifecycle):
    path = lifecycle.root / "retirement.json"
    return path.read_bytes() if path.exists() else None


def write_old_intent(tmp_path):
    assert hashlib.sha256(LEGACY.read_bytes()).hexdigest() == (
        "66ba9d2afdf6de7e418e48a0ff111d867ea3bc999ac44d5df5c212eb39deba92"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", LEGACY_CHILD, str(LEGACY)],
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 73, result.stdout + result.stderr


def broken_first_retry(lifecycle, repo, monkeypatch):
    loader = importlib.machinery.SourceFileLoader("legacy_queue", str(LEGACY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    # The queue code is identical at 5c and 5105. Bind its unchanged bytecode to
    # current record classes, avoiding Pydantic's cross-module type rejection.
    historical_queue = FunctionType(
        module.DatasetLifecycle._queue_retirement.__code__, vars(lifecycle_module)
    )
    with monkeypatch.context() as patch:
        patch.setattr(DatasetLifecycle, "_queue_retirement", historical_queue)
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)


def crash_delete(tmp_path, boundary):
    code = CHILD.replace(
        "if sys.argv[1] == 'import':",
        "if sys.argv[1] == 'delete':\n"
        "    DatasetLifecycle().delete(AppStateRepository(), timeout=0)\n"
        "elif sys.argv[1] == 'import':",
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, "delete"],
        env={**_env(tmp_path), "CRASH_BOUNDARY": boundary},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 73, result.stdout + result.stderr


@pytest.fixture
def legacy_dataset(tmp_path, monkeypatch):
    for key, name in (
        ("TTI_DB_PATH", "health.duckdb"),
        ("TTI_APP_STATE_PATH", "state.sqlite"),
        ("TTI_INGEST_SHARDS", "shards"),
    ):
        monkeypatch.setenv(key, str(tmp_path / name))
    sources = exports(tmp_path)
    _child(tmp_path, "import", sources[0])
    _child(tmp_path, "import", sources[1])
    lifecycle, repo = DatasetLifecycle(), AppStateRepository()
    pointers = [
        json.loads((lifecycle.root / name).read_bytes())
        for name in ("retained.json", "active.json")
    ]
    directories = [lifecycle.root / "generations" / p["generation_id"] for p in pointers]
    # Exact historical source is committed as text so shallow CI need not fetch
    # old Git objects. It executes the real old writer, not hand-written JSON.
    write_old_intent(tmp_path)
    intent = json.loads((lifecycle.root / "deletion.json").read_bytes())
    assert "identities" not in intent
    assert {p["generation_id"] for p in intent["generations"]} == {
        p["generation_id"] for p in pointers
    }
    assert json.loads((lifecycle.root / "active.json").read_bytes()) == pointers[1]
    return lifecycle, repo, sources, pointers, directories


def replace(directory, tmp_path):
    prepared = tmp_path / f"replacement-{directory.name}"
    shutil.copytree(directory, prepared)
    original = tmp_path / f"original-{directory.name}"
    directory.rename(original)
    prepared.rename(directory)
    assert directory.stat().st_ino != original.stat().st_ino
    return original


@pytest.mark.parametrize("replacement", ["none", "retained", "active", "both"])
@pytest.mark.parametrize("order", ["retry_startup", "startup_retry_startup"])
def test_real_old_intent_preserves_both_generations_and_absent_authority(
    legacy_dataset, tmp_path, replacement, order
):
    lifecycle, repo, sources, _, directories = legacy_dataset
    expected = [contents(path) for path in directories]
    for index, kind in enumerate(("retained", "active")):
        if replacement in {kind, "both"}:
            replace(directories[index], tmp_path)
    identities = [path.stat().st_ino for path in directories]
    queue = queue_bytes(lifecycle)
    stable_intent = None
    for attempt in range(3):
        if order.startswith("startup"):
            _child(tmp_path, "startup")
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        _child(tmp_path, "startup")
        assert lifecycle.active() is None
        current = (lifecycle.root / "deletion.json").read_bytes()
        assert json.loads(current).get("identities", []) == []
        if stable_intent is not None:
            assert current == stable_intent
        stable_intent = current
        assert queue_bytes(lifecycle) == queue
        for path, inode, values in zip(directories, identities, expected, strict=True):
            assert path.stat().st_ino == inode
            assert contents(path) == values, f"lost unproven files on attempt {attempt}"
    assert all((source.parent / "sentinel").exists() for source in sources)


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("side_channel", ["preexisting", "broken_first_retry"])
def test_existing_or_poisoned_queue_cannot_backfill_legacy_intent(
    legacy_dataset, tmp_path, monkeypatch, replacement, side_channel
):
    lifecycle, repo, _, pointers, directories = legacy_dataset
    retained, active = directories
    expected = contents(retained), contents(active)
    if side_channel == "preexisting":
        (lifecycle.root / "deletion.json").unlink()
        with lifecycle.writer_lock():
            lifecycle._queue_retirement(lifecycle._read_pointer(lifecycle.root / "retained.json"))
        write_old_intent(tmp_path)
    if replacement:
        replace(retained, tmp_path)
    if side_channel == "broken_first_retry":
        broken_first_retry(lifecycle, repo, monkeypatch)
    proof = queue_bytes(lifecycle)
    assert proof is not None
    assert json.loads(proof)["generations"][0]["pointer"] == pointers[0]
    for _ in range(3):
        _child(tmp_path, "startup")
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert lifecycle.recover(repo) is None
        assert (
            json.loads((lifecycle.root / "deletion.json").read_bytes()).get("identities", []) == []
        )
        assert queue_bytes(lifecycle) == proof
        assert contents(retained) == expected[0]
        assert contents(active) == expected[1]


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize(
    "boundary",
    [
        "deletion_intent_committed",
        "deletion_journal_committed",
        "deletion_pointer_committed",
        "retained_cleared",
        "journal_unlinked",
    ],
)
def test_old_intent_crash_and_repeated_startup_never_create_proof(
    legacy_dataset, tmp_path, replacement, boundary
):
    lifecycle, repo, _, _, directories = legacy_dataset
    if replacement:
        for path in directories:
            replace(path, tmp_path)
    expected = [contents(path) for path in directories]
    queue = queue_bytes(lifecycle)
    crash_delete(tmp_path, boundary)
    for _ in range(3):
        _child(tmp_path, "startup")
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert lifecycle.recover(repo) is None
        assert json.loads((lifecycle.root / "deletion.json").read_bytes())["identities"] == []
        assert queue_bytes(lifecycle) == queue
        assert [contents(path) for path in directories] == expected


@pytest.mark.parametrize("replace_retained", [False, True])
@pytest.mark.parametrize("replace_active", [False, True])
def test_partial_intent_preserves_missing_authority_and_existing_original_identity(
    legacy_dataset, tmp_path, replace_retained, replace_active
):
    lifecycle, repo, _, pointers, directories = legacy_dataset
    retained, active = directories
    expected = [contents(path) for path in directories]
    intent = lifecycle._deletion()
    identity = active.stat()
    intent.identities.append(
        lifecycle_module._Retirement(
            pointer=lifecycle_module._Pointer.model_validate(pointers[1]),
            device=identity.st_dev,
            inode=identity.st_ino,
        )
    )
    with lifecycle.writer_lock():
        lifecycle._replace_record(lifecycle.root / "deletion.json", intent, "fixture_partial")
    if replace_retained:
        replace(retained, tmp_path)
    if replace_active:
        replace(active, tmp_path)
    original_identities = intent.model_dump()["identities"]
    for _ in range(3):
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        _child(tmp_path, "startup")
        assert lifecycle.active() is None
        actual = json.loads((lifecycle.root / "deletion.json").read_bytes())
        assert actual["identities"] == original_identities
        assert queue_bytes(lifecycle) is None
        assert contents(retained) == expected[0]
        assert contents(active) == (expected[1] if replace_active else {})


@pytest.mark.parametrize("queued", [False, True])
def test_new_candidate_can_be_proven_without_promoting_old_members(
    legacy_dataset, tmp_path, queued
):
    lifecycle, repo, sources, pointers, directories = legacy_dataset
    expected = [contents(path) for path in directories]
    _child(tmp_path, "import", sources[2])
    new = lifecycle.active()
    if queued:
        with lifecycle.writer_lock():
            lifecycle._queue_retirement(lifecycle._pointer())
    for _ in range(3):
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        _child(tmp_path, "startup")
        intent = json.loads((lifecycle.root / "deletion.json").read_bytes())
        assert {item["pointer"]["generation_id"] for item in intent["identities"]} == {
            new.dataset.id
        }
        assert {p["generation_id"] for p in intent["generations"]} == {
            new.dataset.id,
            *(p["generation_id"] for p in pointers),
        }
        assert not new.database_path.exists()
        assert [contents(path) for path in directories] == expected


@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize(
    "boundary",
    [
        "retirement_disqualified_written",
        "retirement_disqualified_fsynced",
        "retirement_disqualified_replaced",
        "retirement_disqualified_committed",
    ],
)
def test_empty_or_missing_completion_flushes_disqualification_before_dropping_intent(
    legacy_dataset, tmp_path, monkeypatch, missing, boundary
):
    lifecycle, repo, _, _, directories = legacy_dataset
    saved = {p.name: p.read_bytes() for p in directories[0].iterdir()}
    broken_first_retry(lifecycle, repo, monkeypatch)
    assert queue_bytes(lifecycle) is not None
    intent = (lifecycle.root / "deletion.json").read_bytes()
    for path in directories:
        for file in path.iterdir():
            file.unlink()  # Fixture: no present health files remain to authorize.
        if missing:
            path.rmdir()
    _child(tmp_path, "startup", boundary=boundary, expected=73)
    assert (lifecycle.root / "deletion.json").read_bytes() == intent
    for _ in range(2):
        _child(tmp_path, "startup")
        assert lifecycle.recover(repo) is None
        assert lifecycle.delete(repo, timeout=0) == 0
    assert not (lifecycle.root / "deletion.json").exists()
    assert json.loads(queue_bytes(lifecycle))["generations"] == []
    # Old poisoned proof must not become usable after the negative fence clears.
    directories[0].mkdir(exist_ok=True)
    for name, raw in saved.items():
        (directories[0] / name).write_bytes(raw)
    expected = contents(directories[0])
    for _ in range(2):
        _child(tmp_path, "startup")
        assert contents(directories[0]) == expected


def test_new_proven_intent_reuses_original_retirement_identity_after_replacement(
    legacy_dataset, tmp_path, monkeypatch
):
    lifecycle, repo, _, _, directories = legacy_dataset
    retained, _ = directories
    (lifecycle.root / "deletion.json").unlink()  # Start a fully proven new intent.
    original = retained.stat()
    expected = contents(retained)
    events = []

    def boundary(self, name):
        if name == "deletion_intent_committed" and not events:
            replace(retained, tmp_path)
            events.append(name)

    with monkeypatch.context() as patch:
        patch.setattr(DatasetLifecycle, "_boundary", boundary)
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
    proof = queue_bytes(lifecycle)
    candidate = json.loads(proof)["generations"][0]
    assert candidate["inode"] == original.st_ino != retained.stat().st_ino
    for _ in range(3):
        _child(tmp_path, "startup")
        with pytest.raises(DatasetBusyError):
            lifecycle.delete(repo, timeout=0)
        assert queue_bytes(lifecycle) == proof
        assert contents(retained) == expected
