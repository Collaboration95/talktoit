"""Integration tests for the data/query layer.

Uses a real in-memory DuckDB seeded from the synthetic fixture — per ENGINEERING §2.4.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from app.db.queries import (
    get_comparison,
    get_fallback,
    get_last_workout,
    get_period_summary,
    get_top_workouts,
    get_trend,
)
from app.ingest.parser import ingest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB seeded from the fixture."""
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    return conn


# ---------------------------------------------------------------------------
# get_last_workout
# ---------------------------------------------------------------------------


def test_get_last_running_workout(db: duckdb.DuckDBPyConnection) -> None:
    result = get_last_workout(db, "Running")
    assert result is not None
    assert result.activity_type == "Running"
    assert result.duration_minutes == pytest.approx(45.5)
    assert result.avg_heart_rate == 148
    assert result.max_heart_rate == 178
    assert result.distance_meters == pytest.approx(8500.0)
    assert result.energy_burned_kj == pytest.approx(2500.0)
    assert result.elevation_ascent_meters == pytest.approx(45.0)
    # Workout started at 2026-06-05 07:00 SGT
    assert result.date.year == 2026
    assert result.date.month == 6
    assert result.date.day == 5
    assert result.date.hour == 7


def test_get_last_workout_no_match(db: duckdb.DuckDBPyConnection) -> None:
    result = get_last_workout(db, "Swimming")
    assert result is None


# ---------------------------------------------------------------------------
# get_top_workouts
# ---------------------------------------------------------------------------


def test_get_top_workouts_by_distance_running(db: duckdb.DuckDBPyConnection) -> None:
    result = get_top_workouts(db, "Running", "distance", n=5)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.rank == 1
    assert row.value == pytest.approx(8500.0)
    assert row.unit == "m"
    assert row.secondary_value == pytest.approx(45.5)
    assert row.secondary_unit == "min"


def test_get_top_workouts_by_duration_cycling(db: duckdb.DuckDBPyConnection) -> None:
    result = get_top_workouts(db, "Cycling", "duration", n=5)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.value == pytest.approx(120.0)
    assert row.unit == "min"


def test_get_top_workouts_by_avg_hr(db: duckdb.DuckDBPyConnection) -> None:
    result = get_top_workouts(db, "Running", "avg_hr", n=5)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.value == pytest.approx(148.0)
    assert row.unit == "bpm"


def test_get_top_workouts_empty(db: duckdb.DuckDBPyConnection) -> None:
    result = get_top_workouts(db, "Swimming", "distance", n=5)
    assert result.rows == []


# ---------------------------------------------------------------------------
# get_trend
# ---------------------------------------------------------------------------


def test_get_trend_resting_hr_weekly(db: duckdb.DuckDBPyConnection) -> None:
    result = get_trend(
        db,
        "HKQuantityTypeIdentifierRestingHeartRate",
        "week",
        date(2026, 6, 1),
        date(2026, 6, 10),
    )
    assert result.granularity == "week"
    assert len(result.series) == 2

    # Build a dict for easier assertions
    by_bucket = {p.bucket: p.value for p in result.series}
    # W23: Jun 1 (52), Jun 3 (50), Jun 5 (51) → avg = 51.0
    assert by_bucket["2026-W23"] == pytest.approx(51.0)
    # W24: Jun 8 (49), Jun 10 (48) → avg = 48.5
    assert by_bucket["2026-W24"] == pytest.approx(48.5)


def test_get_trend_resting_hr_daily(db: duckdb.DuckDBPyConnection) -> None:
    result = get_trend(
        db,
        "HKQuantityTypeIdentifierRestingHeartRate",
        "day",
        date(2026, 6, 1),
        date(2026, 6, 10),
    )
    assert len(result.series) == 10

    by_bucket = {p.bucket: p.value for p in result.series}
    assert by_bucket["2026-06-01"] == pytest.approx(52.0)
    assert by_bucket["2026-06-02"] is None  # no record on Jun 2
    assert by_bucket["2026-06-03"] == pytest.approx(50.0)


def test_get_trend_empty_metric(db: duckdb.DuckDBPyConnection) -> None:
    result = get_trend(
        db,
        "HKQuantityTypeIdentifierUnknownMetric",
        "day",
        date(2026, 6, 1),
        date(2026, 6, 10),
    )
    # Buckets generated but all None
    assert len(result.series) == 10
    assert all(p.value is None for p in result.series)


# ---------------------------------------------------------------------------
# get_period_summary
# ---------------------------------------------------------------------------


def test_get_period_summary_june_all(db: duckdb.DuckDBPyConnection) -> None:
    result = get_period_summary(db, date(2026, 6, 1), date(2026, 6, 10))

    by_label = {m.label: m.value for m in result.metrics}
    assert by_label["Workouts"] == pytest.approx(3)
    # 8500 + 45000 = 53500 m → 53.5 km
    assert by_label["Total Distance"] == pytest.approx(53.5)
    # 45.5 + 60.0 + 120.0 = 225.5 min
    assert by_label["Total Duration"] == pytest.approx(225.5)
    # 2500 + 1800 + 3800 = 8100 kJ
    assert by_label["Active Energy"] == pytest.approx(8100.0)


def test_get_period_summary_no_workouts(db: duckdb.DuckDBPyConnection) -> None:
    result = get_period_summary(db, date(2026, 6, 11), date(2026, 6, 20))
    by_label = {m.label: m.value for m in result.metrics}
    # No workouts in this range — sessions may be 0 or None
    sessions = by_label["Workouts"]
    assert sessions == 0 or sessions is None
    assert by_label["Total Distance"] is None
    assert by_label["Total Duration"] is None
    assert by_label["Active Energy"] is None


# ---------------------------------------------------------------------------
# get_comparison
# ---------------------------------------------------------------------------


def test_get_comparison_all_activities(db: duckdb.DuckDBPyConnection) -> None:
    # this period: Jun 6-10 SGT  (Strength Jun 6 + Cycling Jun 8)
    # last period: Jun 1-5 SGT   (Running Jun 5)
    result = get_comparison(
        db,
        this_start=date(2026, 6, 6),
        this_end=date(2026, 6, 10),
        last_start=date(2026, 6, 1),
        last_end=date(2026, 6, 5),
        this_label="Jun 6-10",
        last_label="Jun 1-5",
    )

    by_label = {m.label: m for m in result.metrics}

    sessions_metric = by_label["Sessions"]
    assert sessions_metric.this_value == pytest.approx(2)
    assert sessions_metric.last_value == pytest.approx(1)
    assert sessions_metric.delta == pytest.approx(1)
    assert sessions_metric.direction == "up"

    dist_metric = by_label["Total Distance"]
    # this: Cycling 45000m → 45.0 km
    # last: Running 8500m → 8.5 km
    assert dist_metric.this_value == pytest.approx(45.0)
    assert dist_metric.last_value == pytest.approx(8.5)
    assert dist_metric.delta == pytest.approx(36.5)
    assert dist_metric.direction == "up"


# ---------------------------------------------------------------------------
# get_fallback
# ---------------------------------------------------------------------------


def test_get_fallback() -> None:
    result = get_fallback("test question")
    assert result.question == "test question"
    assert result.table is None
    assert result.text is None


def test_get_fallback_with_text() -> None:
    result = get_fallback("q", text="some answer")
    assert result.text == "some answer"
    assert result.question == "q"
