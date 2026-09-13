"""Child-element attribute-order independence for the V2 byte scanner.

The byte scanner historically matched child elements with fixed attribute
sequences (for example every MetadataEntry had to declare key before value),
which silently dropped valid reordered elements. These tests pin the values for
child elements whose attributes are shuffled, at 1 and 4 workers.
"""

from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2

pytestmark = pytest.mark.ingest_contract

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_reordered_children.xml"


def _snapshot(xml_path: Path, n_workers: int) -> dict[str, list[tuple]]:
    """Ingest the fixture and return value-level snapshots of every child table."""
    db = duckdb.connect(":memory:")
    try:
        ingest_v2(xml_path, db, n_workers=n_workers)
        return {
            "record_metadata": db.execute(
                "SELECT key, value FROM record_metadata ORDER BY key"
            ).fetchall(),
            "hrv_beats": db.execute(
                "SELECT bpm, time_offset FROM hrv_beats ORDER BY time_offset"
            ).fetchall(),
            "workout_events": db.execute(
                "SELECT type, duration, duration_unit FROM workout_events ORDER BY date"
            ).fetchall(),
            "workout_statistics": db.execute(
                "SELECT type, average, minimum, maximum, sum, unit "
                "FROM workout_statistics ORDER BY type"
            ).fetchall(),
            "workout_routes": db.execute(
                "SELECT source_name, file_path FROM workout_routes ORDER BY workout_id"
            ).fetchall(),
            "workout_metadata": db.execute(
                "SELECT key, value FROM workout_metadata ORDER BY key"
            ).fetchall(),
        }
    finally:
        db.close()


@pytest.mark.parametrize("n_workers", [1, 4])
def test_reordered_child_attributes_are_not_dropped(n_workers: int) -> None:
    """Every shuffled child element still stores its values."""
    snapshot = _snapshot(FIXTURE, n_workers)

    assert snapshot["record_metadata"] == [("HKMetadataKeyHeartRateMotionContext", "0")]
    assert snapshot["hrv_beats"] == [(58, 60784.58), (59, 60785.61)]
    assert snapshot["workout_events"] == [("Lap", 22.75, "min")]
    assert snapshot["workout_statistics"] == [
        ("HKQuantityTypeIdentifierActiveEnergyBurned", None, None, None, 2500.0, "kJ"),
        ("HKQuantityTypeIdentifierHeartRate", 148.0, 72.0, 178.0, None, "count/min"),
    ]
    assert snapshot["workout_routes"] == [("Apple Watch", "/workout-routes/route_reordered.gpx")]
    assert snapshot["workout_metadata"] == [
        ("HKAverageMETs", "10.5"),
        ("HKTimeZone", "Asia/Singapore"),
    ]


def test_reordered_child_attributes_are_worker_invariant() -> None:
    """Reordered child elements reconcile identically at 1 and 4 workers."""
    assert _snapshot(FIXTURE, 1) == _snapshot(FIXTURE, 4)
