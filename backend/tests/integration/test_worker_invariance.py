"""Tests for worker count invariance - verifies parallel execution correctness."""

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2


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

    db1.close()
    db4.close()
