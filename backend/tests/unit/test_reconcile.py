"""Synthetic coverage for V2 Parquet loading and ID/FK reconciliation."""

from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from app.db.schema import rebuild_indexes as create_indexes
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
    table: str,
    worker_idx: int,
    rows: list[dict[str, object]],
    schema: pa.Schema,
) -> None:
    """Write one schema-matched synthetic worker shard."""
    path = shard_dir / f"{table}-{worker_idx:04d}-0000.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)


def test_reconcile_rewrites_all_foreign_keys_and_rebuilds_indexes(
    tmp_path: Path, monkeypatch
) -> None:
    """Two worker shards preserve every row and attach children to global IDs."""
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()
    first = datetime(2026, 6, 1, 7, 0)
    second = datetime(2026, 6, 2, 7, 0)
    third = datetime(2026, 6, 3, 7, 0)

    _write_shard(
        shard_dir,
        "records",
        0,
        [
            {
                "worker_idx": 0,
                "local_id": 1,
                "type": "StepCount",
                "source_name": "Phone",
                "source_version": "1",
                "device": None,
                "unit": "count",
                "creation_date": first,
                "start_date": first,
                "end_date": first,
                "value": 10.0,
                "text_value": None,
            },
            {
                "worker_idx": 0,
                "local_id": 2,
                "type": "SleepAnalysis",
                "source_name": "AutoSleep",
                "source_version": "2",
                "device": "Watch",
                "unit": None,
                "creation_date": second,
                "start_date": second,
                "end_date": second,
                "value": None,
                "text_value": "Asleep",
            },
        ],
        RECORDS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "records",
        1,
        [
            {
                "worker_idx": 1,
                "local_id": 1,
                "type": "HeartRateVariability",
                "source_name": "Watch",
                "source_version": "3",
                "device": "Watch",
                "unit": "ms",
                "creation_date": third,
                "start_date": third,
                "end_date": third,
                "value": 42.5,
                "text_value": None,
            }
        ],
        RECORDS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "record_metadata",
        0,
        [
            {"worker_idx": 0, "parent_local_id": 1, "key": "source", "value": "phone"},
            {"worker_idx": 0, "parent_local_id": 2, "key": "state", "value": "asleep"},
        ],
        RECORD_METADATA_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "record_metadata",
        1,
        [{"worker_idx": 1, "parent_local_id": 1, "key": "quality", "value": "good"}],
        RECORD_METADATA_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "hrv_beats",
        1,
        [{"worker_idx": 1, "parent_local_id": 1, "bpm": 58, "time_offset": 1.25}],
        HRV_BEATS_SCHEMA,
    )

    _write_shard(
        shard_dir,
        "workouts",
        0,
        [
            {
                "worker_idx": 0,
                "local_id": 1,
                "activity_type": "Running",
                "duration": 30.0,
                "duration_unit": "min",
                "source_name": "Watch",
                "source_version": "1",
                "device": "Watch",
                "creation_date": first,
                "start_date": first,
                "end_date": second,
            },
            {
                "worker_idx": 0,
                "local_id": 2,
                "activity_type": "Cycling",
                "duration": 1.5,
                "duration_unit": "hr",
                "source_name": "Bike App",
                "source_version": "2",
                "device": None,
                "creation_date": second,
                "start_date": second,
                "end_date": third,
            },
        ],
        WORKOUTS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workouts",
        1,
        [
            {
                "worker_idx": 1,
                "local_id": 1,
                "activity_type": "Yoga",
                "duration": 45.0,
                "duration_unit": "min",
                "source_name": "Phone",
                "source_version": "3",
                "device": "Phone",
                "creation_date": third,
                "start_date": third,
                "end_date": third,
            }
        ],
        WORKOUTS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_events",
        0,
        [
            {
                "worker_idx": 0,
                "parent_local_id": 1,
                "type": "Lap",
                "date": second,
                "duration": 10.0,
                "duration_unit": "min",
            },
            {
                "worker_idx": 0,
                "parent_local_id": 2,
                "type": "Pause",
                "date": third,
                "duration": 5.0,
                "duration_unit": "min",
            },
        ],
        WORKOUT_EVENTS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_events",
        1,
        [
            {
                "worker_idx": 1,
                "parent_local_id": 1,
                "type": "Segment",
                "date": third,
                "duration": 15.0,
                "duration_unit": "min",
            }
        ],
        WORKOUT_EVENTS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_statistics",
        0,
        [
            {
                "worker_idx": 0,
                "parent_local_id": 1,
                "type": "HeartRate",
                "start_date": first,
                "end_date": second,
                "average": 150.0,
                "minimum": 120.0,
                "maximum": 175.0,
                "sum": None,
                "unit": "count/min",
            },
            {
                "worker_idx": 0,
                "parent_local_id": 2,
                "type": "Distance",
                "start_date": second,
                "end_date": third,
                "average": None,
                "minimum": None,
                "maximum": None,
                "sum": 12.5,
                "unit": "km",
            },
        ],
        WORKOUT_STATISTICS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_statistics",
        1,
        [
            {
                "worker_idx": 1,
                "parent_local_id": 1,
                "type": "Energy",
                "start_date": third,
                "end_date": third,
                "average": None,
                "minimum": None,
                "maximum": None,
                "sum": 400.0,
                "unit": "kcal",
            }
        ],
        WORKOUT_STATISTICS_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_routes",
        0,
        [
            {
                "worker_idx": 0,
                "parent_local_id": 1,
                "source_name": "Watch",
                "creation_date": first,
                "start_date": first,
                "end_date": second,
                "file_path": "/routes/run.gpx",
            }
        ],
        WORKOUT_ROUTES_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_routes",
        1,
        [
            {
                "worker_idx": 1,
                "parent_local_id": 1,
                "source_name": "Phone",
                "creation_date": third,
                "start_date": third,
                "end_date": third,
                "file_path": "/routes/yoga.gpx",
            }
        ],
        WORKOUT_ROUTES_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_metadata",
        0,
        [{"worker_idx": 0, "parent_local_id": 2, "key": "indoor", "value": "false"}],
        WORKOUT_METADATA_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "workout_metadata",
        1,
        [{"worker_idx": 1, "parent_local_id": 1, "key": "brand", "value": "Phone"}],
        WORKOUT_METADATA_SCHEMA,
    )
    _write_shard(
        shard_dir,
        "activity_summaries",
        0,
        [
            {
                "date_components": "2026-06-01",
                "active_energy_burned": 500.0,
                "active_energy_burned_goal": 600.0,
                "active_energy_burned_unit": "kcal",
                "apple_move_time": 30.0,
                "apple_move_time_goal": 60.0,
                "apple_exercise_time": 20.0,
                "apple_exercise_time_goal": 30.0,
                "apple_stand_hours": 8,
                "apple_stand_hours_goal": 12,
            },
            {
                "date_components": "2026-06-02",
                "active_energy_burned": None,
                "active_energy_burned_goal": None,
                "active_energy_burned_unit": None,
                "apple_move_time": None,
                "apple_move_time_goal": None,
                "apple_exercise_time": None,
                "apple_exercise_time_goal": None,
                "apple_stand_hours": None,
                "apple_stand_hours_goal": None,
            },
        ],
        ACTIVITY_SUMMARIES_SCHEMA,
    )

    rebuild_observations: list[int] = []

    def observe_rebuild(conn: duckdb.DuckDBPyConnection) -> None:
        """Ensure the reconciler builds indexes only after bulk loading."""
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone() == (3,)
        assert conn.execute("SELECT COUNT(*) FROM duckdb_indexes()").fetchone() == (0,)
        rebuild_observations.append(3)
        create_indexes(conn)

    monkeypatch.setattr("app.ingest.reconcile.rebuild_indexes", observe_rebuild)

    db = duckdb.connect(":memory:")
    try:
        load_shards_into_duckdb(db, shard_dir)
        assert rebuild_observations == [3]

        assert db.execute("SELECT id, type, value FROM records ORDER BY id").fetchall() == [
            (1, "StepCount", 10.0),
            (2, "SleepAnalysis", None),
            (3, "HeartRateVariability", 42.5),
        ]
        assert db.execute(
            "SELECT record_id, key, value FROM record_metadata ORDER BY record_id, key"
        ).fetchall() == [
            (1, "source", "phone"),
            (2, "state", "asleep"),
            (3, "quality", "good"),
        ]
        assert db.execute("SELECT record_id, bpm, time_offset FROM hrv_beats").fetchall() == [
            (3, 58, 1.25)
        ]
        assert db.execute(
            "SELECT id, activity_type, duration, duration_unit FROM workouts ORDER BY id"
        ).fetchall() == [
            (1, "Running", 30.0, "min"),
            (2, "Cycling", 1.5, "hr"),
            (3, "Yoga", 45.0, "min"),
        ]
        assert db.execute(
            "SELECT workout_id, type, duration FROM workout_events ORDER BY workout_id, type"
        ).fetchall() == [(1, "Lap", 10.0), (2, "Pause", 5.0), (3, "Segment", 15.0)]
        assert db.execute(
            "SELECT workout_id, type, sum, unit FROM workout_statistics ORDER BY workout_id"
        ).fetchall() == [
            (1, "HeartRate", None, "count/min"),
            (2, "Distance", 12.5, "km"),
            (3, "Energy", 400.0, "kcal"),
        ]
        assert db.execute(
            "SELECT workout_id, source_name, file_path FROM workout_routes ORDER BY workout_id"
        ).fetchall() == [
            (1, "Watch", "/routes/run.gpx"),
            (3, "Phone", "/routes/yoga.gpx"),
        ]
        assert db.execute(
            "SELECT workout_id, key, value FROM workout_metadata ORDER BY workout_id"
        ).fetchall() == [(2, "indoor", "false"), (3, "brand", "Phone")]
        assert db.execute(
            "SELECT date_components, apple_stand_hours FROM activity_summaries "
            "ORDER BY date_components"
        ).fetchall() == [("2026-06-01", 8), ("2026-06-02", None)]

        indexes = db.execute(
            "SELECT index_name, table_name FROM duckdb_indexes() "
            "WHERE schema_name = 'main' ORDER BY index_name"
        ).fetchall()
        assert indexes == [
            ("idx_records_source", "records"),
            ("idx_records_type_date", "records"),
            ("idx_workout_stats_workout_type", "workout_statistics"),
            ("idx_workouts_type_date", "workouts"),
        ]
    finally:
        db.close()
