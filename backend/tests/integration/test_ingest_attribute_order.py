"""V2 attribute-order independence, asserted across worker counts.

Apple exports normally declare attributes in a stable order, but a producer may
reorder them. The byte-scan worker must record the same canonical values no
matter how an element declares its attributes or how the file is split across
workers. The fixture mirrors sample.xml with every top-level Record/Workout
attribute shuffled.
"""

from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2

pytestmark = pytest.mark.ingest_contract

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_reordered_attributes.xml"


def _snapshot(xml_path: Path, n_workers: int) -> dict[str, list[tuple]]:
    """Ingest the fixture and return value-level snapshots of every table."""
    db = duckdb.connect(":memory:")
    try:
        ingest_v2(xml_path, db, n_workers=n_workers)
        return {
            "records": db.execute(
                "SELECT type, value, text_value FROM records ORDER BY id"
            ).fetchall(),
            "workouts": db.execute(
                "SELECT activity_type, duration, duration_unit FROM workouts ORDER BY id"
            ).fetchall(),
            "workout_events": db.execute(
                "SELECT type, duration, duration_unit FROM workout_events ORDER BY date"
            ).fetchall(),
            "workout_statistics": db.execute(
                "SELECT type, average, minimum, maximum, sum, unit "
                "FROM workout_statistics ORDER BY workout_id, type"
            ).fetchall(),
            "workout_routes": db.execute(
                "SELECT source_name, file_path FROM workout_routes ORDER BY workout_id"
            ).fetchall(),
            "workout_metadata": db.execute(
                "SELECT key, value FROM workout_metadata ORDER BY workout_id, key"
            ).fetchall(),
        }
    finally:
        db.close()


@pytest.mark.parametrize("n_workers", [1, 4])
def test_reordered_attributes_capture_values(n_workers: int) -> None:
    """Shuffled attributes still yield the same typed values, at 1 and 4 workers."""
    snapshot = _snapshot(FIXTURE, n_workers)

    assert snapshot["records"] == [
        ("HKQuantityTypeIdentifierStepCount", 8523.0, None),
        ("HKQuantityTypeIdentifierHeartRate", 65.0, None),
    ]
    assert snapshot["workouts"] == [("Running", 45.5, "min"), ("Cycling", 120.0, "min")]
    assert snapshot["workout_events"] == [("Lap", 22.75, "min")]
    assert snapshot["workout_statistics"] == [
        ("HKQuantityTypeIdentifierHeartRate", 148.0, 72.0, 178.0, None, "count/min"),
        ("HKQuantityTypeIdentifierDistanceCycling", None, None, None, 45000.0, "m"),
    ]
    assert snapshot["workout_routes"] == [("Apple Watch", "/workout-routes/route_reordered.gpx")]
    assert snapshot["workout_metadata"] == [
        ("HKTimeZone", "Asia/Singapore"),
        ("HKWorkoutBrandName", "Strava"),
    ]


def test_attribute_order_is_worker_invariant() -> None:
    """Reordered attributes reconcile to identical rows at 1 and 4 workers."""
    assert _snapshot(FIXTURE, 1) == _snapshot(FIXTURE, 4)
