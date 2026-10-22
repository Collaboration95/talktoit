"""Configured shard roots contain caller data, never disposable run contents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import duckdb
import pytest

from app.ingest import coordinator

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
pytestmark = pytest.mark.ingest_contract


def _root(tmp_path):
    root = tmp_path / "tti_shards_caller_root"
    sibling = root / "tti_shards_other_run"
    sibling.mkdir(parents=True)
    (root / "sentinel.txt").write_text("caller data")
    (sibling / "keep.parquet").write_bytes(b"unrelated")
    return root, sibling


def _assert_preserved(root, sibling):
    assert (root / "sentinel.txt").read_text() == "caller data"
    assert (sibling / "keep.parquet").read_bytes() == b"unrelated"


def _assert_only_empty_claim_metadata(root, sibling):
    public = set()
    for path in root.iterdir():
        if path.name.startswith(".tti_claim_"):
            assert {p.name for p in path.iterdir()} == {"payload"}
            assert (path / "payload").is_dir()
            assert list((path / "payload").iterdir()) == []
        else:
            public.add(path)
    assert public == {root / "sentinel.txt", sibling}


@pytest.mark.parametrize("configuration", ["explicit", "environment", "symlink", "normalized"])
def test_configured_root_is_parent_of_unique_retained_children(
    tmp_path, monkeypatch, configuration
):
    root, sibling = _root(tmp_path)
    configured = root
    if configuration == "symlink":
        configured = tmp_path / "root-link"
        configured.symlink_to(root, target_is_directory=True)
    elif configuration == "normalized":
        configured = sibling / ".."
    kwargs = {"shard_dir": configured}
    if configuration == "environment":
        monkeypatch.setenv("TTI_INGEST_SHARDS", str(configured))
        kwargs = {}
    first = coordinator.ingest(FIXTURE, n_workers=1, cleanup=False, **kwargs)
    first_child = Path(first["shard_dir"])
    assert first_child.parent == root.resolve()
    assert first_child != root
    assert first["records"] == 40
    first_files = {p.name: p.read_bytes() for p in first_child.iterdir()}
    second = coordinator.ingest(FIXTURE, n_workers=1, cleanup=False, **kwargs)
    assert Path(second["shard_dir"]) != first_child
    assert {p.name: p.read_bytes() for p in first_child.iterdir()} == first_files
    _assert_preserved(root, sibling)


@pytest.mark.parametrize("failure", ["parse", "coverage", "reconcile", "syntax", "mmap"])
def test_failure_and_retry_clean_only_owned_run(tmp_path, monkeypatch, failure):
    root, sibling = _root(tmp_path)
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(root))
    seen = []
    real_parse = coordinator.parse_byte_range
    real_load = coordinator.load_shards_into_duckdb

    def parse(**kwargs):
        seen.append(Path(kwargs["shard_dir"]))
        result = real_parse(**kwargs)
        if failure == "parse":
            raise RuntimeError("synthetic parse failure")
        if failure == "coverage":
            result = result._replace(records_count=result.records_count + 1)
        return result

    def load(db, path):
        seen.append(Path(path))
        raise RuntimeError("synthetic reconcile failure")

    with monkeypatch.context() as patch:
        patch.setattr(coordinator, "parse_byte_range", parse)
        if failure == "reconcile":
            patch.setattr(coordinator, "load_shards_into_duckdb", load)
        source = FIXTURE
        if failure in ("syntax", "mmap"):
            source = tmp_path / "invalid.xml"
            source.write_text("<HealthData>" if failure == "syntax" else "")
        expected_error = ValueError if failure == "mmap" else RuntimeError
        with duckdb.connect(":memory:") as db, pytest.raises(expected_error):
            if failure == "mmap":
                coordinator.ingest(source, n_workers=1)
            else:
                coordinator.ingest_v2(source, db, n_workers=1)
    _assert_preserved(root, sibling)
    _assert_only_empty_claim_metadata(root, sibling)
    assert all(not child.exists() for child in seen)
    with duckdb.connect(":memory:") as db:
        monkeypatch.setattr(coordinator, "load_shards_into_duckdb", real_load)
        stats = coordinator.ingest_v2(FIXTURE, db, n_workers=1)
        assert stats["workouts"] == 3
    _assert_preserved(root, sibling)
    _assert_only_empty_claim_metadata(root, sibling)


def test_default_temporary_mode_cleans_success_and_reconcile_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("TTI_INGEST_SHARDS", raising=False)
    with duckdb.connect(":memory:") as db:
        coordinator.ingest_v2(FIXTURE, db, n_workers=1)
    assert list(tmp_path.iterdir()) == []

    def fail(_db, _path):
        raise RuntimeError("synthetic reconciliation failure")

    monkeypatch.setattr(coordinator, "load_shards_into_duckdb", fail)
    with duckdb.connect(":memory:") as db, pytest.raises(RuntimeError):
        coordinator.ingest_v2(FIXTURE, db, n_workers=1)
    assert list(tmp_path.iterdir()) == []


def test_concurrent_runs_cannot_remove_each_others_shards(tmp_path, monkeypatch):
    root, sibling = _root(tmp_path)
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(root))
    barrier = Barrier(2, timeout=30)
    real_load = coordinator.load_shards_into_duckdb
    children = []

    def load(db, path):
        child = Path(path)
        children.append(child)
        (child / "this-run.txt").write_text("owned")
        barrier.wait()
        assert len(set(children)) == 2
        assert all((p / "this-run.txt").exists() for p in children)
        real_load(db, path)
        barrier.wait()

    def run():
        with duckdb.connect(":memory:") as db:
            return coordinator.ingest_v2(FIXTURE, db, n_workers=1)

    monkeypatch.setattr(coordinator, "load_shards_into_duckdb", load)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert [future.result()["records"] for future in futures] == [40, 40]
    # Unknown entries preserve the entire owned child rather than inferring
    # ownership of a caller-created sentinel from its enclosing directory.
    assert all((child / "this-run.txt").read_text() == "owned" for child in children)
    _assert_preserved(root, sibling)


@pytest.mark.parametrize("replace_child", ["internal", "symlink", "directory"])
def test_cleanup_does_not_follow_symlinks_or_replacement_directories(
    tmp_path, monkeypatch, replace_child
):
    root, sibling = _root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("outside data")
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(sibling / ".."))
    real_load = coordinator.load_shards_into_duckdb
    children = []

    def load(db, path):
        child = Path(path)
        children.append(child)
        real_load(db, path)
        if replace_child != "internal":
            child.rename(root / "retained-original")
            if replace_child == "symlink":
                child.symlink_to(outside, target_is_directory=True)
            else:
                child.mkdir()
                (child / "replacement.txt").write_text("replacement data")
        else:
            (child / "external-link").symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(coordinator, "load_shards_into_duckdb", load)
    with duckdb.connect(":memory:") as db:
        coordinator.ingest_v2(FIXTURE, db, n_workers=1)
    assert (outside / "keep.txt").read_text() == "outside data"
    _assert_preserved(root, sibling)
    if replace_child == "symlink":
        assert children[0].is_symlink()
    elif replace_child == "directory":
        assert (children[0] / "replacement.txt").read_text() == "replacement data"
    else:
        assert (children[0] / "external-link").is_symlink()


def test_pool_fallback_preserves_root_and_reconciles_worker_parity(tmp_path, monkeypatch):
    root, sibling = _root(tmp_path)
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(root))

    def unavailable(*_args, **_kwargs):
        raise OSError("synthetic pool unavailable")

    monkeypatch.setattr(coordinator, "_multiprocessing_available", lambda: True)
    monkeypatch.setattr(coordinator, "ProcessPoolExecutor", unavailable)
    snapshots = []
    counts = []
    for workers in (1, 4):
        with duckdb.connect(":memory:") as db:
            stats = coordinator.ingest_v2(FIXTURE, db, n_workers=workers)
            counts.append(
                {key: value for key, value in stats.items() if not key.endswith("seconds")}
            )
            snapshots.append(
                {
                    # Table names come only from this fixed synthetic snapshot list.
                    table: db.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()  # noqa: S608
                    for table in (
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
            )
            assert db.execute(
                "SELECT duration FROM workouts WHERE activity_type = 'Running'"
            ).fetchone() == (45.5,)
    assert counts[0] == counts[1]
    assert snapshots[0] == snapshots[1]
    _assert_preserved(root, sibling)
    _assert_only_empty_claim_metadata(root, sibling)
