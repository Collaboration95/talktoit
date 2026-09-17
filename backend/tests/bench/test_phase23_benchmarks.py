"""Opt-in Phase 2/3 benchmark harness using only generated synthetic data.

The timings here are a smoke harness for collecting comparable local numbers.
They are deliberately not the plan's 6-month or 5x-export performance gates.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from app.ingest.coordinator import ingest_v2

pytestmark = pytest.mark.benchmark


def _write_synthetic_export(path: Path, record_count: int = 256) -> None:
    """Create a deterministic export large enough to cross several boundaries."""
    start = datetime(2024, 1, 1)
    elements: list[str] = []
    for index in range(record_count):
        timestamp = (start + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S +0000")
        metadata = (
            f'<MetadataEntry key="synthetic-index" value="{index}"/>' if index % 4 == 0 else ""
        )
        elements.append(
            f'<Record type="HKQuantityTypeIdentifierStepCount" sourceName="Synthetic" '
            f'startDate="{timestamp}" endDate="{timestamp}" value="{index}">{metadata}</Record>'
        )

    for index in range(8):
        timestamp = (start + timedelta(days=index)).strftime("%Y-%m-%d %H:%M:%S +0000")
        elements.append(
            f'<Workout workoutActivityType="Running" duration="30" durationUnit="min" '
            f'sourceName="Synthetic" startDate="{timestamp}" endDate="{timestamp}">'
            f'<MetadataEntry key="synthetic-workout" value="{index}"/>'
            f'<WorkoutEvent type="Lap" date="{timestamp}" duration="30" durationUnit="min"/>'
            f'<WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" '
            f'startDate="{timestamp}" endDate="{timestamp}" sum="100" unit="kJ"/>'
            "</Workout>"
        )

    path.write_text("<HealthData>" + "".join(elements) + "</HealthData>")


def test_synthetic_phase23_harness_records_worker_timings(tmp_path: Path) -> None:
    """Exercise parsing plus reconciliation at one and four workers."""
    export = tmp_path / "synthetic-phase23.xml"
    _write_synthetic_export(export)
    timings: dict[int, float] = {}
    counts: dict[int, tuple[int, int, int]] = {}

    for workers in (1, 4):
        db = duckdb.connect(":memory:")
        try:
            started = time.perf_counter()
            stats = ingest_v2(export, db, n_workers=workers)
            timings[workers] = time.perf_counter() - started
            counts[workers] = (
                int(stats["records"]),
                int(stats["record_metadata"]),
                int(stats["workouts"]),
            )
        finally:
            db.close()

    assert counts[1] == counts[4] == (256, 64, 8)
    assert all(duration < 10.0 for duration in timings.values())
