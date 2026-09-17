"""Focused integration contracts for the V2 parse and reconciliation phases.

The fixtures in this module are generated in a temporary directory and contain
only synthetic values.  The tests deliberately exercise the phase boundaries:
the parser must produce the same canonical shard rows for different worker
counts, and reconciliation must translate overlapping worker-local IDs while
retaining the schema indexes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

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
from app.ingest.coordinator import ingest
from app.ingest.reconcile import load_shards_into_duckdb

pytestmark = pytest.mark.ingest_contract


def _write_synthetic_export(tmp_path: Path) -> Path:
    """Write a small export with every V2 table represented by child rows."""
    records: list[str] = []
    for index in range(8):
        day = index + 1
        start = f"2026-01-{day:02d} 00:00:00 +0000"
        end = f"2026-01-{day:02d} 00:05:00 +0000"
        children = ""
        if index % 2 == 0:
            children += f'<MetadataEntry key="synthetic-{index}" value="marker-{index}"/>'
        if index in (0, 4):
            children += (
                "<HeartRateVariabilityMetadataList>"
                '<InstantaneousBeatsPerMinute bpm="60" time="0.00"/>'
                '<InstantaneousBeatsPerMinute bpm="61" time="1.25"/>'
                "</HeartRateVariabilityMetadataList>"
            )
        records.append(
            f'<Record type="HKQuantityTypeIdentifierStepCount" '
            f'sourceName="Synthetic Watch" unit="count" creationDate="{start}" '
            f'startDate="{start}" endDate="{end}" value="{index + 1}">'
            f"{children}</Record>"
        )

    workouts: list[str] = []
    for index, activity in enumerate(("Running", "Cycling", "Yoga")):
        day = index + 1
        start = f"2026-02-{day:02d} 06:00:00 +0000"
        end = f"2026-02-{day:02d} 07:00:00 +0000"
        route = ""
        if index in (0, 2):
            route = (
                f'<WorkoutRoute sourceName="Synthetic GPS" creationDate="{end}" '
                f'startDate="{start}" endDate="{end}">'
                f'<FileReference path="/synthetic/route-{index}.gpx"/>'
                "</WorkoutRoute>"
            )
        workouts.append(
            f'<Workout workoutActivityType="{activity}" duration="{30 + index * 15}" '
            f'durationUnit="min" sourceName="Synthetic App" sourceVersion="1" '
            f'creationDate="{start}" startDate="{start}" endDate="{end}">'
            f'<MetadataEntry key="synthetic-workout-{index}" value="w-{index}"/>'
            f'<WorkoutEvent type="Lap" date="{start}" duration="{30 + index * 15}" '
            f'durationUnit="min"/>'
            f'<WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" '
            f'startDate="{start}" endDate="{end}" sum="{100 + index}" unit="kJ"/>'
            f"{route}</Workout>"
        )

    summaries = [
        '<ActivitySummary dateComponents="2026-01-01" activeEnergyBurned="100" '
        'activeEnergyBurnedGoal="200" activeEnergyBurnedUnit="kJ" appleMoveTime="10" '
        'appleMoveTimeGoal="20" appleExerciseTime="5" appleExerciseTimeGoal="10" '
        'appleStandHours="4" appleStandHoursGoal="8"/>',
        '<ActivitySummary dateComponents="2026-01-02" activeEnergyBurned="110" '
        'activeEnergyBurnedGoal="200" activeEnergyBurnedUnit="kJ" appleMoveTime="11" '
        'appleMoveTimeGoal="20" appleExerciseTime="6" appleExerciseTimeGoal="10" '
        'appleStandHours="5" appleStandHoursGoal="8"/>',
    ]
    export = tmp_path / "synthetic-phase-export.xml"
    export.write_text(
        "<HealthData>"
        + "".join(records)
        + "".join(workouts)
        + "".join(summaries)
        + "</HealthData>",
        encoding="utf-8",
    )
    return export


def _shard_rows(shard_dir: Path, table: str) -> list[dict[str, Any]]:
    """Read all Parquet rows for one table prefix."""
    rows: list[dict[str, Any]] = []
    for path in sorted(shard_dir.glob(f"{table}-*.parquet")):
        rows.extend(pq.read_table(path).to_pylist())
    return rows


def _record_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Return stable record identity fields, excluding worker-local IDs."""
    return (
        row["type"],
        row["source_name"],
        row["start_date"],
        row["end_date"],
        row["value"],
        row["text_value"],
    )


def _workout_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Return stable workout identity fields, excluding worker-local IDs."""
    return (
        row["activity_type"],
        row["source_name"],
        row["start_date"],
        row["end_date"],
        row["duration"],
        row["duration_unit"],
    )


def _phase2_snapshot(result: dict[str, Any]) -> dict[str, list[tuple[Any, ...]]]:
    """Canonicalize phase-2 shards, replacing local parent IDs with row keys."""
    shard_dir = Path(result["shard_dir"])
    rows = {
        table: _shard_rows(shard_dir, table)
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
    records_by_id = {
        (row["worker_idx"], row["local_id"]): _record_key(row) for row in rows["records"]
    }
    workouts_by_id = {
        (row["worker_idx"], row["local_id"]): _workout_key(row) for row in rows["workouts"]
    }

    return {
        "records": sorted(
            (*_record_key(row), row["unit"], row["device"]) for row in rows["records"]
        ),
        "record_metadata": sorted(
            (
                records_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["key"],
                row["value"],
            )
            for row in rows["record_metadata"]
        ),
        "hrv_beats": sorted(
            (
                records_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["bpm"],
                row["time_offset"],
            )
            for row in rows["hrv_beats"]
        ),
        "workouts": sorted(
            (*_workout_key(row), row["source_version"], row["device"]) for row in rows["workouts"]
        ),
        "workout_events": sorted(
            (
                workouts_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["type"],
                row["date"],
                row["duration"],
                row["duration_unit"],
            )
            for row in rows["workout_events"]
        ),
        "workout_statistics": sorted(
            (
                workouts_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["type"],
                row["sum"],
                row["unit"],
            )
            for row in rows["workout_statistics"]
        ),
        "workout_routes": sorted(
            (
                workouts_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["source_name"],
                row["file_path"],
            )
            for row in rows["workout_routes"]
        ),
        "workout_metadata": sorted(
            (
                workouts_by_id[(row["worker_idx"], row["parent_local_id"])],
                row["key"],
                row["value"],
            )
            for row in rows["workout_metadata"]
        ),
        "activity_summaries": sorted(
            tuple(
                row[field]
                for field in (
                    "date_components",
                    "active_energy_burned",
                    "active_energy_burned_goal",
                    "active_energy_burned_unit",
                    "apple_move_time",
                    "apple_move_time_goal",
                    "apple_exercise_time",
                    "apple_exercise_time_goal",
                    "apple_stand_hours",
                    "apple_stand_hours_goal",
                )
            )
            for row in rows["activity_summaries"]
        ),
    }


def test_phase2_shards_are_worker_count_invariant(tmp_path: Path) -> None:
    """Phase 2 emits identical canonical rows at one and four workers."""
    export = _write_synthetic_export(tmp_path)
    one_worker = ingest(export, n_workers=1, shard_dir=tmp_path / "one", cleanup=False)
    four_workers = ingest(export, n_workers=4, shard_dir=tmp_path / "four", cleanup=False)

    expected_counts = {
        "records": 8,
        "record_metadata": 4,
        "hrv_beats": 4,
        "workouts": 3,
        "workout_events": 3,
        "workout_statistics": 3,
        "workout_routes": 2,
        "workout_metadata": 3,
        "activity_summaries": 2,
    }
    assert {name: one_worker[name] for name in expected_counts} == expected_counts
    assert {name: four_workers[name] for name in expected_counts} == expected_counts
    assert len(list(Path(four_workers["shard_dir"]).glob("records-*.parquet"))) > 1
    assert _phase2_snapshot(one_worker) == _phase2_snapshot(four_workers)


def _write_shard(
    shard_dir: Path, filename: str, rows: list[dict[str, Any]], schema: pa.Schema
) -> None:
    """Write one typed synthetic shard."""
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), shard_dir / filename)


def test_phase3_reconciliation_handles_overlapping_ids_and_indexes(tmp_path: Path) -> None:
    """Phase 3 rewrites every child FK and recreates the expected indexes."""
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()
    first = datetime(2026, 3, 1, 6, 0)
    second = datetime(2026, 3, 2, 6, 0)

    for worker_idx, start, value, activity in (
        (0, first, 11.0, "Running"),
        (1, second, 22.0, "Cycling"),
    ):
        end = start.replace(hour=7)
        worker = f"{worker_idx:04d}-0000.parquet"
        _write_shard(
            shard_dir,
            f"records-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "local_id": 1,
                    "type": "HKQuantityTypeIdentifierStepCount",
                    "source_name": f"Synthetic {worker_idx}",
                    "source_version": "1",
                    "device": None,
                    "unit": "count",
                    "creation_date": start,
                    "start_date": start,
                    "end_date": end,
                    "value": value,
                    "text_value": None,
                }
            ],
            RECORDS_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"record_metadata-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "key": f"record-{worker_idx}",
                    "value": f"value-{worker_idx}",
                }
            ],
            RECORD_METADATA_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"hrv_beats-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "bpm": 60 + worker_idx,
                    "time_offset": float(worker_idx),
                }
            ],
            HRV_BEATS_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"workouts-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "local_id": 1,
                    "activity_type": activity,
                    "duration": 30.0 + worker_idx,
                    "duration_unit": "min",
                    "source_name": f"Synthetic App {worker_idx}",
                    "source_version": "1",
                    "device": None,
                    "creation_date": start,
                    "start_date": start,
                    "end_date": end,
                }
            ],
            WORKOUTS_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"workout_events-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "type": "Lap",
                    "date": start,
                    "duration": 15.0 + worker_idx,
                    "duration_unit": "min",
                }
            ],
            WORKOUT_EVENTS_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"workout_statistics-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "type": "HKQuantityTypeIdentifierActiveEnergyBurned",
                    "start_date": start,
                    "end_date": end,
                    "average": None,
                    "minimum": None,
                    "maximum": None,
                    "sum": 100.0 + worker_idx,
                    "unit": "kJ",
                }
            ],
            WORKOUT_STATISTICS_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"workout_routes-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "source_name": f"Synthetic GPS {worker_idx}",
                    "creation_date": end,
                    "start_date": start,
                    "end_date": end,
                    "file_path": f"/synthetic/route-{worker_idx}.gpx",
                }
            ],
            WORKOUT_ROUTES_SCHEMA,
        )
        _write_shard(
            shard_dir,
            f"workout_metadata-{worker}",
            [
                {
                    "worker_idx": worker_idx,
                    "parent_local_id": 1,
                    "key": f"workout-{worker_idx}",
                    "value": f"metadata-{worker_idx}",
                }
            ],
            WORKOUT_METADATA_SCHEMA,
        )

    _write_shard(
        shard_dir,
        "activity_summaries-0000-0000.parquet",
        [
            {
                "date_components": "2026-03-01",
                "active_energy_burned": 100.0,
                "active_energy_burned_goal": 200.0,
                "active_energy_burned_unit": "kJ",
                "apple_move_time": 20.0,
                "apple_move_time_goal": 30.0,
                "apple_exercise_time": 10.0,
                "apple_exercise_time_goal": 15.0,
                "apple_stand_hours": 8,
                "apple_stand_hours_goal": 10,
            }
        ],
        ACTIVITY_SUMMARIES_SCHEMA,
    )

    conn = duckdb.connect(":memory:")
    try:
        load_shards_into_duckdb(conn, shard_dir)

        assert conn.execute("SELECT id, value FROM records ORDER BY id").fetchall() == [
            (1, 11.0),
            (2, 22.0),
        ]
        assert conn.execute(
            "SELECT r.value, rm.key, rm.value FROM record_metadata rm "
            "JOIN records r ON r.id = rm.record_id ORDER BY r.id"
        ).fetchall() == [(11.0, "record-0", "value-0"), (22.0, "record-1", "value-1")]
        assert conn.execute(
            "SELECT r.value, h.bpm FROM hrv_beats h JOIN records r ON r.id = h.record_id "
            "ORDER BY r.id"
        ).fetchall() == [(11.0, 60), (22.0, 61)]
        assert conn.execute(
            "SELECT w.activity_type, e.duration FROM workout_events e "
            "JOIN workouts w ON w.id = e.workout_id ORDER BY w.id"
        ).fetchall() == [("Running", 15.0), ("Cycling", 16.0)]
        assert conn.execute(
            "SELECT w.activity_type, s.sum FROM workout_statistics s "
            "JOIN workouts w ON w.id = s.workout_id ORDER BY w.id"
        ).fetchall() == [("Running", 100.0), ("Cycling", 101.0)]
        assert conn.execute(
            "SELECT w.activity_type, r.file_path FROM workout_routes r "
            "JOIN workouts w ON w.id = r.workout_id ORDER BY w.id"
        ).fetchall() == [
            ("Running", "/synthetic/route-0.gpx"),
            ("Cycling", "/synthetic/route-1.gpx"),
        ]
        assert conn.execute(
            "SELECT w.activity_type, m.key, m.value FROM workout_metadata m "
            "JOIN workouts w ON w.id = m.workout_id ORDER BY w.id"
        ).fetchall() == [
            ("Running", "workout-0", "metadata-0"),
            ("Cycling", "workout-1", "metadata-1"),
        ]

        orphan_queries = (
            "SELECT COUNT(*) FROM record_metadata child LEFT JOIN records parent "
            "ON child.record_id = parent.id WHERE parent.id IS NULL",
            "SELECT COUNT(*) FROM hrv_beats child LEFT JOIN records parent "
            "ON child.record_id = parent.id WHERE parent.id IS NULL",
            "SELECT COUNT(*) FROM workout_events child LEFT JOIN workouts parent "
            "ON child.workout_id = parent.id WHERE parent.id IS NULL",
            "SELECT COUNT(*) FROM workout_statistics child LEFT JOIN workouts parent "
            "ON child.workout_id = parent.id WHERE parent.id IS NULL",
            "SELECT COUNT(*) FROM workout_routes child LEFT JOIN workouts parent "
            "ON child.workout_id = parent.id WHERE parent.id IS NULL",
            "SELECT COUNT(*) FROM workout_metadata child LEFT JOIN workouts parent "
            "ON child.workout_id = parent.id WHERE parent.id IS NULL",
        )
        for query in orphan_queries:
            assert conn.execute(query).fetchone() == (0,)

        indexes = set(
            conn.execute(
                "SELECT index_name, table_name FROM duckdb_indexes() "
                "WHERE index_name IN ("
                "'idx_records_type_date', 'idx_records_source', "
                "'idx_workouts_type_date', 'idx_workout_stats_workout_type')"
            ).fetchall()
        )
        assert indexes == {
            ("idx_records_type_date", "records"),
            ("idx_records_source", "records"),
            ("idx_workouts_type_date", "workouts"),
            ("idx_workout_stats_workout_type", "workout_statistics"),
        }

        # Reconciliation starts from a clean schema, so a second load cannot
        # duplicate rows and must leave the same indexes available.
        load_shards_into_duckdb(conn, shard_dir)
        assert conn.execute("SELECT COUNT(*) FROM records").fetchone() == (2,)
        assert conn.execute("SELECT COUNT(*) FROM workouts").fetchone() == (2,)
        assert conn.execute("SELECT COUNT(*) FROM activity_summaries").fetchone() == (1,)
    finally:
        conn.close()
