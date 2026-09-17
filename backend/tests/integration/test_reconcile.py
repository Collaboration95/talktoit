"""Synthetic coverage for DuckDB Phase 3 shard reconciliation."""

# ruff: noqa: S608 - test table names and columns come from closed tuples above

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.db.schema import SQL_CREATE_TABLES
from app.ingest.bytescan import (
    ACTIVITY_SUMMARIES_SCHEMA,
    HRV_BEATS_SCHEMA,
    RECORD_METADATA_SCHEMA,
    RECORDS_SCHEMA,
    WORKOUT_EVENTS_SCHEMA,
    WORKOUT_METADATA_SCHEMA,
    WORKOUT_ROUTES_SCHEMA,
    WORKOUT_STATISTICS_SCHEMA,
    WORKOUTS_SCHEMA,
)
from app.ingest.reconcile import load_shards_into_duckdb


def _write_shard(
    shard_dir: Path,
    table_name: str,
    worker_idx: int,
    rows: list[dict[str, object]],
    schema: pa.Schema,
) -> None:
    """Write one small worker shard using the production Arrow schema."""
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, shard_dir / f"{table_name}-{worker_idx:04d}-0000.parquet")


def _write_synthetic_shards(
    shard_dir: Path, workers: int = 3, records_per_worker: int = 250
) -> dict[str, int]:
    """Create bounded multi-worker shards covering every reconciled table."""
    counts = {
        "records": 0,
        "record_metadata": 0,
        "hrv_beats": 0,
        "workouts": 0,
        "workout_events": 0,
        "workout_statistics": 0,
        "workout_routes": 0,
        "workout_metadata": 0,
        "activity_summaries": 0,
    }

    for worker_idx in range(workers):
        records: list[dict[str, object]] = []
        record_metadata: list[dict[str, object]] = []
        hrv_beats: list[dict[str, object]] = []
        workouts: list[dict[str, object]] = []
        workout_events: list[dict[str, object]] = []
        workout_statistics: list[dict[str, object]] = []
        workout_routes: list[dict[str, object]] = []
        workout_metadata: list[dict[str, object]] = []

        for local_id in range(1, records_per_worker + 1):
            start = datetime(2024, 1, 1) + timedelta(days=worker_idx, minutes=local_id)
            records.append(
                {
                    "worker_idx": worker_idx,
                    "local_id": local_id,
                    "type": f"SyntheticRecord-{worker_idx}-{local_id}",
                    "source_name": f"SyntheticSource-{worker_idx}",
                    "source_version": "1",
                    "device": None,
                    "unit": "count",
                    "creation_date": start,
                    "start_date": start,
                    "end_date": start + timedelta(minutes=1),
                    "value": float(local_id),
                    "text_value": None,
                }
            )
            if local_id in (1, records_per_worker):
                record_metadata.append(
                    {
                        "worker_idx": worker_idx,
                        "parent_local_id": local_id,
                        "key": "synthetic-key",
                        "value": f"record-{worker_idx}-{local_id}",
                    }
                )
            if local_id % 50 == 0:
                hrv_beats.append(
                    {
                        "worker_idx": worker_idx,
                        "parent_local_id": local_id,
                        "bpm": 60 + worker_idx,
                        "time_offset": 1.5,
                    }
                )

        for local_id in range(1, 7):
            start = datetime(2024, 2, 1) + timedelta(days=worker_idx, minutes=local_id)
            workouts.append(
                {
                    "worker_idx": worker_idx,
                    "local_id": local_id,
                    "activity_type": f"SyntheticWorkout-{worker_idx}-{local_id}",
                    "duration": 30.0,
                    "duration_unit": "min",
                    "source_name": f"SyntheticWorkoutSource-{worker_idx}",
                    "source_version": "1",
                    "device": None,
                    "creation_date": start,
                    "start_date": start,
                    "end_date": start + timedelta(minutes=30),
                }
            )
            workout_events.append(
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": local_id,
                    "type": "SyntheticLap",
                    "date": start + timedelta(minutes=10),
                    "duration": 10.0,
                    "duration_unit": "min",
                }
            )
            workout_statistics.append(
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": local_id,
                    "type": "SyntheticDistance",
                    "start_date": start,
                    "end_date": start + timedelta(minutes=30),
                    "average": None,
                    "minimum": None,
                    "maximum": None,
                    "sum": 5.0,
                    "unit": "km",
                }
            )
            workout_routes.append(
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": local_id,
                    "source_name": "SyntheticRouteSource",
                    "creation_date": start,
                    "start_date": start,
                    "end_date": start + timedelta(minutes=30),
                    "file_path": f"/synthetic/{worker_idx}/{local_id}.gpx",
                }
            )
            workout_metadata.append(
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": local_id,
                    "key": "synthetic-workout-key",
                    "value": f"workout-{worker_idx}-{local_id}",
                }
            )

        activity_summary = {
            "date_components": f"2024-03-{worker_idx + 1:02d}",
            "active_energy_burned": 100.0,
            "active_energy_burned_goal": 200.0,
            "active_energy_burned_unit": "kJ",
            "apple_move_time": 30.0,
            "apple_move_time_goal": 60.0,
            "apple_exercise_time": 20.0,
            "apple_exercise_time_goal": 30.0,
            "apple_stand_hours": 8,
            "apple_stand_hours_goal": 12,
        }

        shard_rows = {
            "records": (records, RECORDS_SCHEMA),
            "record_metadata": (record_metadata, RECORD_METADATA_SCHEMA),
            "hrv_beats": (hrv_beats, HRV_BEATS_SCHEMA),
            "workouts": (workouts, WORKOUTS_SCHEMA),
            "workout_events": (workout_events, WORKOUT_EVENTS_SCHEMA),
            "workout_statistics": (workout_statistics, WORKOUT_STATISTICS_SCHEMA),
            "workout_routes": (workout_routes, WORKOUT_ROUTES_SCHEMA),
            "workout_metadata": (workout_metadata, WORKOUT_METADATA_SCHEMA),
            "activity_summaries": ([activity_summary], ACTIVITY_SUMMARIES_SCHEMA),
        }
        for table_name, (rows, schema) in shard_rows.items():
            _write_shard(shard_dir, table_name, worker_idx, rows, schema)
            counts[table_name] += len(rows)

    return counts


def test_reconcile_preserves_all_fks_and_rebuilds_indexes(tmp_path: Path) -> None:
    """Multi-shard synthetic data retains every parent and child relationship."""
    expected_counts = _write_synthetic_shards(tmp_path)
    db = duckdb.connect(":memory:")
    try:
        load_shards_into_duckdb(db, tmp_path)

        for table_name, expected_count in expected_counts.items():
            assert db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone() == (expected_count,)

        record_ids = db.execute("SELECT id FROM records ORDER BY id").fetchall()
        assert record_ids == [
            (record_id,) for record_id in range(1, expected_counts["records"] + 1)
        ]
        workout_ids = db.execute("SELECT id FROM workouts ORDER BY id").fetchall()
        assert workout_ids == [
            (workout_id,) for workout_id in range(1, expected_counts["workouts"] + 1)
        ]

        fk_checks = (
            ("record_metadata", "record_id", "records", "id"),
            ("hrv_beats", "record_id", "records", "id"),
            ("workout_events", "workout_id", "workouts", "id"),
            ("workout_statistics", "workout_id", "workouts", "id"),
            ("workout_routes", "workout_id", "workouts", "id"),
            ("workout_metadata", "workout_id", "workouts", "id"),
        )
        for child, child_key, parent, parent_key in fk_checks:
            orphan_count = db.execute(
                f"SELECT COUNT(*) FROM {child} c "
                f"LEFT JOIN {parent} p ON c.{child_key} = p.{parent_key} "
                f"WHERE p.{parent_key} IS NULL"
            ).fetchone()
            assert orphan_count == (0,), child

        metadata_values = db.execute(
            "SELECT r.type, rm.value FROM record_metadata rm "
            "JOIN records r ON r.id = rm.record_id "
            "ORDER BY r.type"
        ).fetchall()
        assert metadata_values[0][1].startswith("record-")
        assert len(metadata_values) == expected_counts["record_metadata"]

        indexes = {
            row[0] for row in db.execute("SELECT index_name FROM duckdb_indexes()").fetchall()
        }
        assert indexes >= {
            "idx_records_type_date",
            "idx_records_source",
            "idx_workouts_type_date",
            "idx_workout_stats_workout_type",
        }
    finally:
        db.close()


def test_reconcile_rejects_orphan_fk_without_destroying_existing_schema(tmp_path: Path) -> None:
    """An invalid child key fails loudly and rolls back the staging reset/load."""
    _write_shard(
        tmp_path,
        "records",
        0,
        [
            {
                "worker_idx": 0,
                "local_id": 1,
                "type": "SyntheticRecord",
                "source_name": "SyntheticSource",
                "source_version": None,
                "device": None,
                "unit": None,
                "creation_date": datetime(2024, 1, 1),
                "start_date": datetime(2024, 1, 1),
                "end_date": datetime(2024, 1, 1, 0, 1),
                "value": 1.0,
                "text_value": None,
            }
        ],
        RECORDS_SCHEMA,
    )
    _write_shard(
        tmp_path,
        "record_metadata",
        0,
        [{"worker_idx": 0, "parent_local_id": 999, "key": "bad", "value": "bad"}],
        RECORD_METADATA_SCHEMA,
    )

    db = duckdb.connect(":memory:")
    try:
        db.execute(SQL_CREATE_TABLES)
        db.execute(
            "INSERT INTO records "
            "VALUES (77, 'Existing', 'ExistingSource', NULL, NULL, NULL, NULL, "
            "TIMESTAMP '2020-01-01', TIMESTAMP '2020-01-01 00:01:00', 1.0, NULL)"
        )

        with pytest.raises(ValueError, match="row-count mismatch for record_metadata"):
            load_shards_into_duckdb(db, tmp_path)

        assert db.execute("SELECT id, type FROM records").fetchall() == [(77, "Existing")]
        assert db.execute("SELECT COUNT(*) FROM record_metadata").fetchone() == (0,)
    finally:
        db.close()


def test_reconcile_rejects_missing_parent_and_duplicate_local_keys(tmp_path: Path) -> None:
    """Malformed Option A inputs fail before they can produce ambiguous FKs."""
    _write_shard(
        tmp_path,
        "record_metadata",
        0,
        [{"worker_idx": 0, "parent_local_id": 1, "key": "k", "value": "v"}],
        RECORD_METADATA_SCHEMA,
    )
    db = duckdb.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="missing parent data"):
            load_shards_into_duckdb(db, tmp_path)
    finally:
        db.close()

    for path in tmp_path.glob("*.parquet"):
        path.unlink()
    _write_shard(
        tmp_path,
        "records",
        0,
        [
            {
                "worker_idx": 0,
                "local_id": 1,
                "type": "SyntheticRecord-A",
                "source_name": "SyntheticSource",
                "source_version": None,
                "device": None,
                "unit": None,
                "creation_date": datetime(2024, 1, 1),
                "start_date": datetime(2024, 1, 1),
                "end_date": datetime(2024, 1, 1, 0, 1),
                "value": 1.0,
                "text_value": None,
            },
            {
                "worker_idx": 0,
                "local_id": 1,
                "type": "SyntheticRecord-B",
                "source_name": "SyntheticSource",
                "source_version": None,
                "device": None,
                "unit": None,
                "creation_date": datetime(2024, 1, 2),
                "start_date": datetime(2024, 1, 2),
                "end_date": datetime(2024, 1, 2, 0, 1),
                "value": 2.0,
                "text_value": None,
            },
        ],
        RECORDS_SCHEMA,
    )
    db = duckdb.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="Duplicate worker-local keys"):
            load_shards_into_duckdb(db, tmp_path)
    finally:
        db.close()
