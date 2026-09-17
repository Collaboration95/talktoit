"""Focused Phase 2/3 verification against the synthetic export fixture.

These checks intentionally compare business content and parent/child joins rather
than surrogate IDs.  Reconciliation is allowed to choose different global IDs as
long as the same child rows remain attached to the same parent content.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2

pytestmark = pytest.mark.ingest_contract

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"

EXPECTED_INDEXES = {
    "idx_records_source",
    "idx_records_type_date",
    "idx_workout_stats_workout_type",
    "idx_workouts_type_date",
}

COUNT_KEYS = (
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


def _snapshot(db: duckdb.DuckDBPyConnection) -> dict[str, list[tuple]]:
    """Return canonical rows with parent content in place of generated IDs."""
    return {
        "records": db.execute(
            "SELECT type, source_name, source_version, device, unit, creation_date, "
            "start_date, end_date, value, text_value FROM records "
            "ORDER BY type, source_name, start_date, end_date, value, text_value"
        ).fetchall(),
        "record_metadata": db.execute(
            "SELECT r.type, r.source_name, r.start_date, rm.key, rm.value "
            "FROM record_metadata rm JOIN records r ON r.id = rm.record_id "
            "ORDER BY r.type, r.source_name, r.start_date, rm.key, rm.value"
        ).fetchall(),
        "hrv_beats": db.execute(
            "SELECT r.type, r.source_name, r.start_date, h.bpm, h.time_offset "
            "FROM hrv_beats h JOIN records r ON r.id = h.record_id "
            "ORDER BY r.type, r.source_name, r.start_date, h.time_offset"
        ).fetchall(),
        "workouts": db.execute(
            "SELECT activity_type, duration, duration_unit, source_name, source_version, "
            "device, creation_date, start_date, end_date FROM workouts "
            "ORDER BY activity_type, source_name, start_date"
        ).fetchall(),
        "workout_events": db.execute(
            "SELECT w.activity_type, w.start_date, e.type, e.date, e.duration, e.duration_unit "
            "FROM workout_events e JOIN workouts w ON w.id = e.workout_id "
            "ORDER BY w.activity_type, w.start_date, e.date, e.type"
        ).fetchall(),
        "workout_statistics": db.execute(
            "SELECT w.activity_type, w.start_date, s.type, s.start_date, s.end_date, "
            "s.average, s.minimum, s.maximum, s.sum, s.unit "
            "FROM workout_statistics s JOIN workouts w ON w.id = s.workout_id "
            "ORDER BY w.activity_type, w.start_date, s.type"
        ).fetchall(),
        "workout_routes": db.execute(
            "SELECT w.activity_type, w.start_date, r.source_name, r.creation_date, "
            "r.start_date, r.end_date, r.file_path "
            "FROM workout_routes r JOIN workouts w ON w.id = r.workout_id "
            "ORDER BY w.activity_type, w.start_date, r.file_path"
        ).fetchall(),
        "workout_metadata": db.execute(
            "SELECT w.activity_type, w.start_date, m.key, m.value "
            "FROM workout_metadata m JOIN workouts w ON w.id = m.workout_id "
            "ORDER BY w.activity_type, w.start_date, m.key, m.value"
        ).fetchall(),
        "activity_summaries": db.execute(
            "SELECT date_components, active_energy_burned, active_energy_burned_goal, "
            "active_energy_burned_unit, apple_move_time, apple_move_time_goal, "
            "apple_exercise_time, apple_exercise_time_goal, apple_stand_hours, "
            "apple_stand_hours_goal FROM activity_summaries ORDER BY date_components"
        ).fetchall(),
    }


def test_worker_counts_preserve_canonical_rows_and_relationships() -> None:
    """Worker counts 1..8 preserve every canonical row and child relationship."""
    snapshots: list[dict[str, list[tuple]]] = []
    stats_by_worker: dict[int, dict[str, int]] = {}

    for workers in (1, 2, 4, 6, 8):
        db = duckdb.connect(":memory:")
        try:
            stats = ingest_v2(FIXTURE, db, n_workers=workers)
            stats_by_worker[workers] = {key: int(stats[key]) for key in COUNT_KEYS}
            snapshots.append(_snapshot(db))
        finally:
            db.close()

    assert len({tuple(stats[key] for key in COUNT_KEYS) for stats in stats_by_worker.values()}) == 1
    assert all(snapshot == snapshots[0] for snapshot in snapshots[1:])


def test_reconciliation_assigns_valid_ids_and_recreates_indexes() -> None:
    """Phase 3 yields contiguous IDs, valid FKs, and all four declared indexes."""
    db = duckdb.connect(":memory:")
    try:
        stats = ingest_v2(FIXTURE, db, n_workers=8)

        assert db.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM records").fetchone() == (
            1,
            stats["records"],
            stats["records"],
        )
        assert db.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM workouts").fetchone() == (
            1,
            stats["workouts"],
            stats["workouts"],
        )

        orphan_queries = (
            "SELECT COUNT(*) FROM record_metadata c "
            "LEFT JOIN records p ON p.id = c.record_id WHERE p.id IS NULL",
            "SELECT COUNT(*) FROM hrv_beats c "
            "LEFT JOIN records p ON p.id = c.record_id WHERE p.id IS NULL",
            "SELECT COUNT(*) FROM workout_events c "
            "LEFT JOIN workouts p ON p.id = c.workout_id WHERE p.id IS NULL",
            "SELECT COUNT(*) FROM workout_statistics c "
            "LEFT JOIN workouts p ON p.id = c.workout_id WHERE p.id IS NULL",
            "SELECT COUNT(*) FROM workout_routes c "
            "LEFT JOIN workouts p ON p.id = c.workout_id WHERE p.id IS NULL",
            "SELECT COUNT(*) FROM workout_metadata c "
            "LEFT JOIN workouts p ON p.id = c.workout_id WHERE p.id IS NULL",
        )
        for query in orphan_queries:
            assert db.execute(query).fetchone() == (0,)

        actual_indexes = {
            row[0]
            for row in db.execute(
                "SELECT index_name FROM duckdb_indexes() WHERE index_name IS NOT NULL"
            ).fetchall()
        }
        assert EXPECTED_INDEXES <= actual_indexes
    finally:
        db.close()
