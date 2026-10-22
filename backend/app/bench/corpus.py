"""Bounded, streamed synthetic exports and private correctness oracles."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import duckdb


@dataclass(frozen=True)
class CorpusSpec:
    """Versioned corpus recipe; no external export can be supplied."""

    name: Literal["small", "representative"]
    records: int
    workouts: int
    days: int
    seed: int = 137


CASES = {
    "small": CorpusSpec("small", records=2048, workouts=64, days=28),
    "representative": CorpusSpec("representative", records=500_000, workouts=8192, days=180),
}


@dataclass(frozen=True)
class Corpus:
    """Private oracles, separated from the public report."""

    sha256: str
    source_bytes: int
    counts: dict[str, int]
    step_total: int
    duration_total: int


def write_corpus(path: Path, spec: CorpusSpec) -> Corpus:
    """Stream fixed-seed numeric/category records and nested workout children."""
    if min(spec.records, spec.workouts, spec.days) < 1:
        raise ValueError("corpus_invalid")
    rng = random.Random(spec.seed)  # noqa: S311 - reproducible synthetic data, not secrets
    origin = datetime(2024, 1, 1)
    step_total = 0
    duration_total = 0
    digest = hashlib.sha256()
    with path.open("wb") as handle:

        def emit(element: str) -> None:
            data = (element + "\n").encode()
            digest.update(data)
            handle.write(data)

        emit('<HealthData locale="en_US">')
        for index in range(spec.records):
            stamp = origin + timedelta(days=index % spec.days, minutes=rng.randrange(1440))
            start = stamp.strftime("%Y-%m-%d %H:%M:%S +0800")
            end = (stamp + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S +0800")
            kind = index % 4
            value = 0 if index % 17 == 0 else rng.randrange(1, 200)
            metric, unit = (
                ("HKQuantityTypeIdentifierStepCount", "count"),
                ("HKQuantityTypeIdentifierRestingHeartRate", "count/min"),
                ("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "ms"),
                ("HKCategoryTypeIdentifierSleepAnalysis", ""),
            )[kind]
            raw_value = str(value) if kind != 3 else "HKCategoryValueSleepAnalysisAsleepCore"
            if kind == 0:
                step_total += value
            child = '<MetadataEntry key="synthetic" value="generated"/>' if index % 4 == 0 else ""
            # Vary attribute order, including nested/self-closing records.
            attrs = [
                f'type="{metric}"',
                'sourceName="Synthetic"',
                f'unit="{unit}"',
                f'startDate="{start}"',
                f'endDate="{end}"',
                f'value="{raw_value}"',
            ]
            if index % 2:
                attrs.reverse()
            joined = " ".join(attrs)
            emit(f"<Record {joined}>{child}</Record>" if child else f"<Record {joined}/>")
        for index in range(spec.workouts):
            stamp = origin + timedelta(days=index % spec.days, seconds=index)
            start = stamp.strftime("%Y-%m-%d %H:%M:%S +0800")
            end = (stamp + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S +0800")
            duration = 20 + index % 71
            duration_total += duration
            activity = "Running" if index % 2 == 0 else "Cycling"
            source = "Synthetic" if index % 3 else "SyntheticOther"
            emit(
                f'<Workout workoutActivityType="{activity}" duration="{duration}" '
                f'durationUnit="min" sourceName="{source}" startDate="{start}" endDate="{end}">'
            )
            emit('<MetadataEntry key="HKElevationAscended" value="10"/>')
            emit(f'<WorkoutEvent type="Lap" date="{start}" duration="1" durationUnit="min"/>')
            for metric, values in (
                (
                    "HKQuantityTypeIdentifierHeartRate",
                    'average="120" maximum="150" unit="count/min"',
                ),
                ("HKQuantityTypeIdentifierDistanceWalkingRunning", 'sum="5" unit="km"'),
                ("HKQuantityTypeIdentifierActiveEnergyBurned", 'sum="100" unit="kcal"'),
            ):
                emit(
                    f'<WorkoutStatistics type="{metric}" startDate="{start}" '
                    f'endDate="{end}" {values}/>'
                )
            emit("</Workout>")
        for day in range(spec.days):
            stamp = (origin + timedelta(days=day)).strftime("%Y-%m-%d")
            emit(
                f'<ActivitySummary dateComponents="{stamp}" activeEnergyBurned="100" '
                'activeEnergyBurnedGoal="200" activeEnergyBurnedUnit="kJ" '
                'appleMoveTime="30" appleMoveTimeGoal="60" '
                'appleExerciseTime="30" appleExerciseTimeGoal="30" '
                'appleStandHours="8" appleStandHoursGoal="12"/>'
            )
        emit("</HealthData>")
    return Corpus(
        digest.hexdigest(),
        path.stat().st_size,
        {
            "records": spec.records,
            "record_metadata": (spec.records + 3) // 4,
            "hrv_beats": 0,
            "workouts": spec.workouts,
            "workout_events": spec.workouts,
            "workout_statistics": spec.workouts * 3,
            "workout_routes": 0,
            "workout_metadata": spec.workouts,
            "activity_summaries": spec.days,
        },
        step_total,
        duration_total,
    )


def verify_database(conn: duckdb.DuckDBPyConnection, spec: CorpusSpec, corpus: Corpus) -> None:
    """Reject count, known-value or relationship drift without printing rows."""
    for table, count in corpus.counts.items():
        # Identifiers come only from the generator's closed table set.
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        if row != (count,):
            raise RuntimeError("synthetic_parity_failed")
    for child, parent, key in (
        ("record_metadata", "records", "record_id"),
        ("hrv_beats", "records", "record_id"),
        ("workout_metadata", "workouts", "workout_id"),
        ("workout_statistics", "workouts", "workout_id"),
        ("workout_events", "workouts", "workout_id"),
        ("workout_routes", "workouts", "workout_id"),
    ):
        sql = (
            f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p "  # noqa: S608
            f"ON c.{key} = p.id WHERE p.id IS NULL"
        )
        if conn.execute(sql).fetchone() != (0,):
            raise RuntimeError("synthetic_parity_failed")
    steps = conn.execute(
        "SELECT sum(value) FROM records WHERE type = 'HKQuantityTypeIdentifierStepCount'"
    ).fetchone()
    durations = conn.execute("SELECT sum(duration), count(*) FROM workouts").fetchone()
    if steps != (corpus.step_total,) or durations != (corpus.duration_total, spec.workouts):
        raise RuntimeError("synthetic_parity_failed")
