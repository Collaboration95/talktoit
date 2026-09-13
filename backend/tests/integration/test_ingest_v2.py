"""Integration tests for the V2 parallel byte-scan ingestion pipeline."""

from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2

pytestmark = pytest.mark.ingest_contract


@pytest.fixture
def sample_xml_path():
    """Path to the sample XML fixture."""
    return Path(__file__).parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def temp_db():
    """Create a temporary in-memory DuckDB instance."""
    db = duckdb.connect(":memory:")
    yield db
    db.close()


def test_v2_ingest_row_counts(sample_xml_path, temp_db):
    """Test that V2 ingestion produces correct row counts."""
    stats = ingest_v2(sample_xml_path, temp_db)

    # Verify row counts from stats
    assert stats["records"] == 40
    assert stats["record_metadata"] == 7
    assert stats["hrv_beats"] == 7
    assert stats["workouts"] == 3
    assert stats["workout_events"] == 6
    assert stats["workout_statistics"] == 8
    assert stats["workout_routes"] == 2
    assert stats["workout_metadata"] == 12
    assert stats["activity_summaries"] == 5

    activities = temp_db.execute(
        "SELECT activity_type, duration, duration_unit FROM workouts ORDER BY id"
    ).fetchall()
    assert activities == [
        ("Running", 45.5, "min"),
        ("TraditionalStrengthTraining", 60.0, "min"),
        ("Cycling", 120.0, "min"),
    ]
    assert temp_db.execute("SELECT COUNT(*) FROM hrv_beats").fetchone()[0] == 7

    # Verify timing stats are present
    assert "parse_time_seconds" in stats
    assert "load_time_seconds" in stats
    assert "total_time_seconds" in stats
    assert stats["parse_time_seconds"] > 0
    assert stats["load_time_seconds"] > 0
    assert stats["total_time_seconds"] > 0


def test_v2_ingest_records_table(sample_xml_path, temp_db):
    """Test that records table is correctly populated."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM records").fetchone()
    assert result[0] == 40

    # Check that IDs are sequential
    result = temp_db.execute("SELECT MIN(id), MAX(id) FROM records").fetchone()
    assert result[0] == 1
    assert result[1] == 40

    # Check a specific record type
    result = temp_db.execute("""
        SELECT COUNT(*) FROM records
        WHERE type = 'HKQuantityTypeIdentifierStepCount'
    """).fetchone()
    assert result[0] == 10


def test_v2_ingest_record_metadata(sample_xml_path, temp_db):
    """Test that record_metadata table is correctly populated with FK relationships."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM record_metadata").fetchone()
    assert result[0] == 7

    # Check that all record_ids exist in records table
    result = temp_db.execute("""
        SELECT COUNT(*) FROM record_metadata rm
        LEFT JOIN records r ON rm.record_id = r.id
        WHERE r.id IS NULL
    """).fetchone()
    assert result[0] == 0, "All record_metadata entries should have valid record_id FK"


def test_v2_ingest_workouts(sample_xml_path, temp_db):
    """Test that workouts table is correctly populated."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM workouts").fetchone()
    assert result[0] == 3

    # Check that IDs are sequential
    result = temp_db.execute("SELECT MIN(id), MAX(id) FROM workouts").fetchone()
    assert result[0] == 1
    assert result[1] == 3


def test_v2_ingest_workout_events(sample_xml_path, temp_db):
    """Test that workout_events table is correctly populated with FK relationships."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM workout_events").fetchone()
    assert result[0] == 6

    # Value-level assertion: row counts alone hid the empty activity_type defect.
    events = temp_db.execute(
        "SELECT workout_id, type, duration, duration_unit FROM workout_events "
        "ORDER BY workout_id, date"
    ).fetchall()
    assert events == [
        (1, "Lap", 22.75, "min"),
        (1, "Lap", 22.75, "min"),
        (3, "Lap", 30.0, "min"),
        (3, "Lap", 30.0, "min"),
        (3, "Lap", 30.0, "min"),
        (3, "Lap", 30.0, "min"),
    ]

    # Check that all workout_ids exist in workouts table
    result = temp_db.execute("""
        SELECT COUNT(*) FROM workout_events we
        LEFT JOIN workouts w ON we.workout_id = w.id
        WHERE w.id IS NULL
    """).fetchone()
    assert result[0] == 0, "All workout_events entries should have valid workout_id FK"


def test_v2_ingest_workout_statistics(sample_xml_path, temp_db):
    """Test that workout_statistics table is correctly populated."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM workout_statistics").fetchone()
    assert result[0] == 8

    # Heart-rate statistics carry average/minimum/maximum; energy and distance
    # rows carry a sum. Values, units, and parent linkage must all survive.
    heart_rate = temp_db.execute(
        "SELECT workout_id, average, minimum, maximum, sum, unit FROM workout_statistics "
        "WHERE type = 'HKQuantityTypeIdentifierHeartRate' ORDER BY workout_id"
    ).fetchall()
    assert heart_rate == [
        (1, 148.0, 72.0, 178.0, None, "count/min"),
        (2, 125.0, 68.0, 162.0, None, "count/min"),
        (3, 138.0, 95.0, 172.0, None, "count/min"),
    ]
    energy = temp_db.execute(
        "SELECT workout_id, sum, unit FROM workout_statistics "
        "WHERE type = 'HKQuantityTypeIdentifierActiveEnergyBurned' ORDER BY workout_id"
    ).fetchall()
    assert energy == [(1, 2500.0, "kJ"), (2, 1800.0, "kJ"), (3, 3800.0, "kJ")]


def test_v2_ingest_child_tables_capture_values(sample_xml_path, temp_db):
    """Routes, workout metadata, and HRV beats must store real values.

    Row-count-only assertions let an empty value column ship. These checks pin
    the parsed values for the remaining child tables.
    """
    ingest_v2(sample_xml_path, temp_db)

    routes = temp_db.execute(
        "SELECT workout_id, source_name, file_path FROM workout_routes ORDER BY workout_id"
    ).fetchall()
    assert routes == [
        (1, "Apple Watch", "/workout-routes/route_2026-06-05_7.00am.gpx"),
        (3, "Strava", "/workout-routes/route_2026-06-08_6.00pm.gpx"),
    ]

    metadata = temp_db.execute(
        "SELECT value FROM workout_metadata WHERE workout_id = 3 AND key = 'HKExternalUUID'"
    ).fetchone()
    assert metadata == ("abc-123-strava-cycling",)
    keys = {
        row[0] for row in temp_db.execute("SELECT DISTINCT key FROM workout_metadata").fetchall()
    }
    assert keys == {
        "HKTimeZone",
        "HKAverageMETs",
        "HKElevationAscended",
        "HKIndoorWorkout",
        "HKWorkoutBrandName",
        "HKExternalUUID",
    }

    beats = temp_db.execute(
        "SELECT bpm, time_offset FROM hrv_beats WHERE record_id = 35 ORDER BY time_offset"
    ).fetchall()
    assert beats == [(58, 0.0), (59, 1.03), (57, 2.08), (60, 3.05)]


def test_v2_ingest_activity_summaries(sample_xml_path, temp_db):
    """Test that activity_summaries table is correctly populated."""
    ingest_v2(sample_xml_path, temp_db)

    # Check total count
    result = temp_db.execute("SELECT COUNT(*) FROM activity_summaries").fetchone()
    assert result[0] == 5


def test_v2_ingest_idempotency(sample_xml_path, temp_db):
    """Test that V2 ingestion is idempotent (can be run multiple times)."""
    # Run ingestion twice
    stats1 = ingest_v2(sample_xml_path, temp_db)
    stats2 = ingest_v2(sample_xml_path, temp_db)

    # Both runs should produce identical row counts
    assert stats1["records"] == stats2["records"]
    assert stats1["record_metadata"] == stats2["record_metadata"]
    assert stats1["workouts"] == stats2["workouts"]
    assert stats1["activity_summaries"] == stats2["activity_summaries"]

    # Verify database state after second run
    result = temp_db.execute("SELECT COUNT(*) FROM records").fetchone()
    assert result[0] == 40, "Second run should not duplicate data"
