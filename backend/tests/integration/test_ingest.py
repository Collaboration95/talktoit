"""Integration tests for the ingestion pipeline.

These tests use a real DuckDB (in-memory) seeded from the synthetic fixture.
The database is never mocked — per ENGINEERING §2.4.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.ingest.parser import ingest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB for each test."""
    return duckdb.connect(":memory:")


def test_ingest_fixture_row_counts(db: duckdb.DuckDBPyConnection) -> None:
    """Ingesting the synthetic fixture populates every table with exact counts."""
    result = ingest(str(FIXTURE), db)

    # Verify per-table row counts match the fixture
    # 10 steps + 10 HR + 5 resting HR + 5 energy + 5 distance + 3 HRV + 3 sleep
    assert result.records == 40
    assert result.record_metadata >= 5  # HR motion context (1) + sleep records (2) with metadata
    assert result.hrv_beats == 7  # 4 + 3 = 7 beats total across 2 HRV records with beats
    assert result.workouts == 3
    assert result.workout_events == 6  # Running: 2 laps, Cycling: 4 laps
    assert result.workout_statistics == 8  # Running: 3, Strength: 2, Cycling: 3
    assert result.workout_routes == 2  # Running + Cycling have routes
    assert result.workout_metadata >= 9  # Running: 4, Strength: 3, Cycling: 5
    assert result.activity_summaries == 5


def test_ingest_record_values(db: duckdb.DuckDBPyConnection) -> None:
    """Assert known record values are stored correctly."""
    ingest(str(FIXTURE), db)

    # First step count record
    row = db.execute(
        "SELECT type, value, unit FROM records WHERE type='HKQuantityTypeIdentifierStepCount' "
        "ORDER BY start_date LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "HKQuantityTypeIdentifierStepCount"
    assert row[1] == 8523.0
    assert row[2] == "count"

    # Resting HR records
    count = db.execute(
        "SELECT COUNT(*) FROM records WHERE type='HKQuantityTypeIdentifierRestingHeartRate'"
    ).fetchone()
    assert count is not None and count[0] == 5

    # Sleep category record (value is NULL for category types)
    row = db.execute(
        "SELECT type, value FROM records WHERE type='HKCategoryTypeIdentifierSleepAnalysis' LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "HKCategoryTypeIdentifierSleepAnalysis"
    assert row[1] is None  # category type → no value


def test_ingest_workout_values(db: duckdb.DuckDBPyConnection) -> None:
    """Assert known workout attributes are stored correctly."""
    ingest(str(FIXTURE), db)

    # Running workout
    row = db.execute(
        "SELECT activity_type, duration, start_date FROM workouts "
        "WHERE activity_type='Running' LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "Running"
    assert row[1] == 45.5
    from datetime import datetime

    assert isinstance(row[2], datetime)  # DuckDB returns datetime objects

    # Workout statistics — HR for running
    row = db.execute(
        "SELECT average, minimum, maximum, sum, unit FROM workout_statistics ws "
        "JOIN workouts w ON ws.workout_id = w.id "
        "WHERE w.activity_type='Running' AND ws.type='HKQuantityTypeIdentifierHeartRate'"
    ).fetchone()
    assert row is not None
    assert row[0] == 148.0  # average
    assert row[1] == 72.0  # minimum
    assert row[2] == 178.0  # maximum
    assert row[3] is None  # sum (not applicable for HR)
    assert "count/min" in (row[4] or "")

    # Cycling distance (Strava workout)
    row = db.execute(
        "SELECT sum FROM workout_statistics ws "
        "JOIN workouts w ON ws.workout_id = w.id "
        "WHERE w.activity_type='Cycling' AND ws.type='HKQuantityTypeIdentifierDistanceCycling'"
    ).fetchone()
    assert row is not None
    assert row[0] == 45000.0  # 45 km in metres


def test_ingest_workout_metadata(db: duckdb.DuckDBPyConnection) -> None:
    """Assert workout metadata is stored."""
    ingest(str(FIXTURE), db)

    # Strava workout has brand metadata
    row = db.execute(
        "SELECT value FROM workout_metadata wm "
        "JOIN workouts w ON wm.workout_id = w.id "
        "WHERE w.activity_type='Cycling' AND wm.key='HKWorkoutBrandName'"
    ).fetchone()
    assert row is not None
    assert row[0] == "Strava"


def test_ingest_workout_route(db: duckdb.DuckDBPyConnection) -> None:
    """Assert GPS route file references are stored."""
    ingest(str(FIXTURE), db)

    count = db.execute("SELECT COUNT(*) FROM workout_routes").fetchone()
    assert count is not None and count[0] == 2

    # Running route has a file path
    row = db.execute(
        "SELECT file_path FROM workout_routes wr "
        "JOIN workouts w ON wr.workout_id = w.id "
        "WHERE w.activity_type='Running'"
    ).fetchone()
    assert row is not None
    assert row[0] == "/workout-routes/route_2026-06-05_7.00am.gpx"


def test_ingest_activity_summaries(db: duckdb.DuckDBPyConnection) -> None:
    """Assert activity ring data is stored."""
    ingest(str(FIXTURE), db)

    count = db.execute("SELECT COUNT(*) FROM activity_summaries").fetchone()
    assert count is not None and count[0] == 5

    # June 5th — the most active day
    row = db.execute(
        "SELECT active_energy_burned, apple_exercise_time, apple_stand_hours "
        "FROM activity_summaries WHERE date_components='2026-06-05'"
    ).fetchone()
    assert row is not None
    assert row[0] == 3200.0
    assert row[1] == 55.0
    assert row[2] == 14


def test_ingest_idempotent(db: duckdb.DuckDBPyConnection) -> None:
    """Re-running ingest on the same DB produces the same final state."""
    result1 = ingest(str(FIXTURE), db)
    result2 = ingest(str(FIXTURE), db)

    # Row counts must be identical (not doubled)
    assert result2.records == result1.records
    assert result2.workouts == result1.workouts
    assert result2.activity_summaries == result1.activity_summaries

    # Verify the actual count in the DB hasn't changed
    count = db.execute("SELECT COUNT(*) FROM records").fetchone()
    assert count is not None and count[0] == result1.records


def test_ingest_hrv_beats(db: duckdb.DuckDBPyConnection) -> None:
    """Assert HRV beat data is stored correctly."""
    ingest(str(FIXTURE), db)

    count = db.execute("SELECT COUNT(*) FROM hrv_beats").fetchone()
    assert count is not None and count[0] == 7

    # First beat of the first HRV record should have specific values
    row = db.execute(
        "SELECT bpm, time_offset FROM hrv_beats ORDER BY record_id, time_offset LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == 58
    assert row[1] == 0.0
