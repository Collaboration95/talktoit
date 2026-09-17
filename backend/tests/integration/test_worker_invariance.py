"""Tests for worker count invariance - verifies parallel execution correctness."""

from itertools import pairwise
from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2, split_boundaries


@pytest.fixture
def sample_xml():
    """Path to sample XML file."""
    return "tests/fixtures/sample.xml"


@pytest.fixture
def db():
    """Create an in-memory DuckDB database."""
    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


def test_worker_count_invariance_1_worker(sample_xml, db):
    """Test ingestion with 1 worker."""
    stats = ingest_v2(sample_xml, db, n_workers=1)

    # Verify row counts
    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5


def test_worker_count_invariance_2_workers(sample_xml, db):
    """Test ingestion with 2 workers."""
    stats = ingest_v2(sample_xml, db, n_workers=2)

    # Verify row counts - should be identical to 1 worker
    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5


def test_worker_count_invariance_4_workers(sample_xml, db):
    """Test ingestion with 4 workers."""
    stats = ingest_v2(sample_xml, db, n_workers=4)

    # Verify row counts - should be identical to 1 worker
    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5


def test_worker_count_invariance_6_workers(sample_xml, db):
    """Test ingestion with 6 workers."""
    stats = ingest_v2(sample_xml, db, n_workers=6)

    # Verify row counts - should be identical to 1 worker
    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5


def test_worker_count_invariance_8_workers(sample_xml, db):
    """Test the configured worker-count ceiling on the fixture."""
    stats = ingest_v2(sample_xml, db, n_workers=8)

    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5


@pytest.mark.parametrize("n_workers", [1, 2, 4, 6, 8])
def test_boundaries_are_contiguous_and_start_on_top_level_tags(sample_xml, n_workers):
    """Worker ranges cover the file without splitting a top-level element."""
    data = Path(sample_xml).read_bytes()
    ranges = split_boundaries(data, n_workers)

    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(data)
    assert all(previous[1] == current[0] for previous, current in pairwise(ranges))
    for start, _ in ranges[1:]:
        assert data.startswith((b"<Record", b"<Workout", b"<ActivitySummary"), start)


def test_data_consistency_across_worker_counts(sample_xml):
    """Test that data is consistent across different worker counts."""
    # Run with 1 worker
    db1 = duckdb.connect(":memory:")
    stats1 = ingest_v2(sample_xml, db1, n_workers=1)

    # Get all record IDs with 1 worker
    records_1 = db1.execute("SELECT id, type, value FROM records ORDER BY id").fetchall()

    # Run with 4 workers
    db4 = duckdb.connect(":memory:")
    stats4 = ingest_v2(sample_xml, db4, n_workers=4)

    # Get all record IDs with 4 workers
    records_4 = db4.execute("SELECT id, type, value FROM records ORDER BY id").fetchall()

    # Verify counts match
    assert len(records_1) == len(records_4)
    assert stats1["records"] == stats4["records"]

    # Verify data is identical (IDs might be assigned differently, but data should match)
    types_1 = sorted([r[1] for r in records_1])
    types_4 = sorted([r[1] for r in records_4])
    assert types_1 == types_4

    values_1 = sorted([r[2] for r in records_1 if r[2] is not None])
    values_4 = sorted([r[2] for r in records_4 if r[2] is not None])
    assert values_1 == values_4

    workouts_1 = db1.execute(
        "SELECT activity_type, duration, duration_unit FROM workouts ORDER BY id"
    ).fetchall()
    workouts_4 = db4.execute(
        "SELECT activity_type, duration, duration_unit FROM workouts ORDER BY id"
    ).fetchall()
    assert workouts_1 == workouts_4
    assert {row[0] for row in workouts_1} == {"Running", "Cycling", "TraditionalStrengthTraining"}

    # Child tables must reconcile to identical rows, not just identical counts.
    child_queries = {
        "record_metadata": "SELECT record_id, key, value FROM record_metadata "
        "ORDER BY record_id, key, value",
        "hrv_beats": "SELECT record_id, bpm, time_offset FROM hrv_beats "
        "ORDER BY record_id, time_offset",
        "workout_events": "SELECT workout_id, type, duration, duration_unit FROM workout_events "
        "ORDER BY workout_id, date",
        "workout_statistics": "SELECT workout_id, type, average, minimum, maximum, sum, unit "
        "FROM workout_statistics ORDER BY workout_id, type",
        "workout_routes": "SELECT workout_id, source_name, file_path FROM workout_routes "
        "ORDER BY workout_id",
        "workout_metadata": "SELECT workout_id, key, value FROM workout_metadata "
        "ORDER BY workout_id, key",
    }
    for table, query in child_queries.items():
        rows_1 = db1.execute(query).fetchall()
        rows_4 = db4.execute(query).fetchall()
        assert rows_1, f"{table} should not be empty for the fixture"
        assert rows_1 == rows_4, f"{table} rows differ between 1 and 4 workers"

    db1.close()
    db4.close()
