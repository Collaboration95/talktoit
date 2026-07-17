"""Integration tests for the dashboard API layer.

Uses a real in-memory DuckDB seeded from the synthetic fixture — per ENGINEERING §2.4.
Tests both the query logic directly and the HTTP endpoints via ASGI transport.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from pathlib import Path

import duckdb
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.aggregations import DEFAULT_TZ, utc_bounds
from app.ingest.parser import ingest
from app.main import app

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    """Create a fresh in-memory DuckDB seeded from the fixture."""
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    return conn


@pytest_asyncio.fixture
async def client(db: duckdb.DuckDBPyConnection) -> AsyncClient:
    """HTTP client with DB dependency overridden to use the fixture DB."""
    from app.api.dashboard import _get_conn

    def _override_get_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
        yield db

    app.dependency_overrides[_get_conn] = _override_get_conn
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(_get_conn, None)


# ---------------------------------------------------------------------------
# SQL-level unit tests (direct query)
# ---------------------------------------------------------------------------


def test_activity_summary_returns_days(db: duckdb.DuckDBPyConnection) -> None:
    """Fixture has 5 activity summary days; query the whole range."""
    rows = db.execute(
        """
        SELECT date_components FROM activity_summaries
        WHERE date_components >= ? AND date_components <= ?
        ORDER BY date_components DESC
        """,
        ["2026-06-01", "2026-06-10"],
    ).fetchall()
    assert len(rows) == 5
    dates = [r[0] for r in rows]
    assert "2026-06-10" in dates
    assert "2026-06-01" in dates


def test_workouts_list_returns_workouts(db: duckdb.DuckDBPyConnection) -> None:
    """Fixture has 3 workouts; query the whole June range."""
    utc_start, utc_end = utc_bounds(date(2026, 6, 1), date(2026, 6, 30), DEFAULT_TZ)
    rows = db.execute(
        """
        SELECT w.id, w.activity_type, w.start_date, w.duration, w.duration_unit,
            hr.average AS avg_hr,
            dist.sum AS distance_m,
            energy.sum AS energy_kj
        FROM workouts w
        LEFT JOIN workout_statistics hr
            ON hr.workout_id = w.id
            AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
        LEFT JOIN (
            SELECT workout_id, sum FROM workout_statistics
            WHERE type IN ('HKQuantityTypeIdentifierDistanceWalkingRunning',
                           'HKQuantityTypeIdentifierDistanceCycling',
                           'HKQuantityTypeIdentifierDistanceSwimming')
        ) dist ON dist.workout_id = w.id
        LEFT JOIN workout_statistics energy
            ON energy.workout_id = w.id
            AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
        WHERE w.start_date >= ? AND w.start_date < ?
        ORDER BY w.start_date DESC
        LIMIT 100
        """,
        [utc_start, utc_end],
    ).fetchall()
    assert len(rows) == 3
    activity_types = [r[1] for r in rows]
    assert "Running" in activity_types
    assert "Cycling" in activity_types
    assert "TraditionalStrengthTraining" in activity_types


def test_steps_trend_daily(db: duckdb.DuckDBPyConnection) -> None:
    """Step records for June 1-10 should yield 10 non-null values."""
    from app.db.aggregations import bucket_key, generate_buckets, to_local_dt

    utc_start, utc_end = utc_bounds(date(2026, 6, 1), date(2026, 6, 10), DEFAULT_TZ)
    rows = db.execute(
        """
        SELECT start_date, value FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ? AND value IS NOT NULL
        ORDER BY start_date
        """,
        ["HKQuantityTypeIdentifierStepCount", utc_start, utc_end],
    ).fetchall()

    bucket_values: dict[str, list[float]] = {}
    for start_date_utc, value in rows:
        local_dt = to_local_dt(start_date_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), "day")
        bucket_values.setdefault(key, []).append(float(value))

    all_buckets = generate_buckets(date(2026, 6, 1), date(2026, 6, 10), "day")
    assert len(all_buckets) == 10

    # All 10 June 1-10 days should have step data
    for bucket in all_buckets:
        assert bucket in bucket_values, f"Missing steps data for {bucket}"


def test_resting_hr_trend_weekly(db: duckdb.DuckDBPyConnection) -> None:
    """5 resting HR records in June should aggregate into 2 ISO weeks."""
    from app.db.aggregations import bucket_key, generate_buckets, to_local_dt

    utc_start, utc_end = utc_bounds(date(2026, 6, 1), date(2026, 6, 10), DEFAULT_TZ)
    rows = db.execute(
        """
        SELECT start_date, value FROM records
        WHERE type = ? AND start_date >= ? AND start_date < ? AND value IS NOT NULL
        ORDER BY start_date
        """,
        ["HKQuantityTypeIdentifierRestingHeartRate", utc_start, utc_end],
    ).fetchall()

    bucket_values: dict[str, list[float]] = {}
    for start_date_utc, value in rows:
        local_dt = to_local_dt(start_date_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), "week")
        bucket_values.setdefault(key, []).append(float(value))

    # June 1 is Monday of W23 and June 8 is Monday of W24
    all_buckets = generate_buckets(date(2026, 6, 1), date(2026, 6, 10), "week")
    assert len(all_buckets) == 2

    # Should have at least 2 weekly buckets with data
    non_empty_buckets = [b for b in all_buckets if b in bucket_values]
    assert len(non_empty_buckets) >= 2

    # Verify averages are in plausible range
    for bucket_key_str, vals in bucket_values.items():
        avg = sum(vals) / len(vals)
        assert 40 <= avg <= 70, f"Unexpected resting HR average {avg} for {bucket_key_str}"


def test_sleep_trend(db: duckdb.DuckDBPyConnection) -> None:
    """Fixture has 3 sleep records; should compute sleep hours per day."""
    from app.db.aggregations import bucket_key, generate_buckets, to_local_dt

    utc_start, utc_end = utc_bounds(date(2026, 6, 1), date(2026, 6, 10), DEFAULT_TZ)
    rows = db.execute(
        """
        SELECT start_date, end_date FROM records
        WHERE type = 'HKCategoryTypeIdentifierSleepAnalysis'
          AND start_date >= ? AND start_date < ?
        ORDER BY start_date
        """,
        [utc_start, utc_end],
    ).fetchall()

    assert len(rows) == 3

    bucket_sums: dict[str, float] = {}
    for start_dt_utc, end_dt_utc in rows:
        duration_hours = (end_dt_utc - start_dt_utc).total_seconds() / 3600.0
        local_dt = to_local_dt(start_dt_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), "day")
        bucket_sums[key] = bucket_sums.get(key, 0.0) + duration_hours

    # Should have sleep hours for some days
    assert len(bucket_sums) > 0
    for key, hours in bucket_sums.items():
        assert hours > 0, f"Zero sleep hours for {key}"
        assert hours < 24, f"More than 24 sleep hours for {key}"

    all_buckets = generate_buckets(date(2026, 6, 1), date(2026, 6, 10), "day")
    non_null_count = sum(1 for b in all_buckets if b in bucket_sums)
    assert non_null_count >= 2


def test_capabilities_fixture(db: duckdb.DuckDBPyConnection) -> None:
    """Fixture has resting HR, steps, HRV, sleep, and workouts."""
    rows = db.execute(
        """
        SELECT type, COUNT(*) AS cnt FROM records
        WHERE type IN ('HKQuantityTypeIdentifierRestingHeartRate',
                       'HKQuantityTypeIdentifierStepCount',
                       'HKCategoryTypeIdentifierSleepAnalysis',
                       'HKQuantityTypeIdentifierHeartRateVariabilitySDNN')
        GROUP BY type
        """,
    ).fetchall()
    present_types = {row[0] for row in rows if row[1] > 0}

    assert "HKQuantityTypeIdentifierRestingHeartRate" in present_types
    assert "HKQuantityTypeIdentifierStepCount" in present_types
    assert "HKCategoryTypeIdentifierSleepAnalysis" in present_types
    assert "HKQuantityTypeIdentifierHeartRateVariabilitySDNN" in present_types

    workout_row = db.execute("SELECT COUNT(*) FROM workouts").fetchone()
    assert workout_row is not None
    assert workout_row[0] > 0


def test_activity_summary_empty_range(db: duckdb.DuckDBPyConnection) -> None:
    """A date range with no data should return empty list."""
    rows = db.execute(
        """
        SELECT date_components FROM activity_summaries
        WHERE date_components >= ? AND date_components <= ?
        """,
        ["2020-01-01", "2020-01-07"],
    ).fetchall()
    assert rows == []


def test_workouts_empty_range(db: duckdb.DuckDBPyConnection) -> None:
    """A date range with no workouts should return empty list."""
    utc_start, utc_end = utc_bounds(date(2020, 1, 1), date(2020, 1, 7), DEFAULT_TZ)
    rows = db.execute(
        "SELECT id FROM workouts WHERE start_date >= ? AND start_date < ?",
        [utc_start, utc_end],
    ).fetchall()
    assert rows == []


# ---------------------------------------------------------------------------
# HTTP-level integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_summary(client: AsyncClient) -> None:
    """GET /api/dashboard/summary returns days list."""
    r = await client.get(
        "/api/dashboard/summary", params={"start": "2026-06-01", "end": "2026-06-10"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "days" in data
    assert isinstance(data["days"], list)
    assert len(data["days"]) == 5


@pytest.mark.asyncio
async def test_http_workouts(client: AsyncClient) -> None:
    """GET /api/dashboard/workouts returns workouts list."""
    r = await client.get(
        "/api/dashboard/workouts", params={"start": "2026-06-01", "end": "2026-06-30"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "workouts" in data
    assert len(data["workouts"]) == 3
    workout = data["workouts"][0]
    assert "activity_type" in workout
    assert "date" in workout
    assert "duration_minutes" in workout


@pytest.mark.asyncio
async def test_http_steps(client: AsyncClient) -> None:
    """GET /api/dashboard/steps returns a trend response."""
    r = await client.get(
        "/api/dashboard/steps",
        params={"start": "2026-06-01", "end": "2026-06-10", "granularity": "day"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["metric_label"] == "Steps"
    assert data["granularity"] == "day"
    assert len(data["series"]) == 10


@pytest.mark.asyncio
async def test_default_dashboard_window_anchors_to_latest_local_data(client: AsyncClient) -> None:
    """A stale export must not generate a window ending at the computer clock."""
    response = await client.get("/api/dashboard/steps")

    assert response.status_code == 200
    series = response.json()["series"]
    assert series[-1]["bucket"] == "2026-06-10"
    assert any(point["value"] is not None for point in series)


@pytest.mark.asyncio
async def test_http_heart(client: AsyncClient) -> None:
    """GET /api/dashboard/heart returns a trend response."""
    r = await client.get(
        "/api/dashboard/heart",
        params={"start": "2026-06-01", "end": "2026-06-10", "granularity": "week"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["metric_label"] == "Resting HR"
    assert data["granularity"] == "week"
    assert len(data["series"]) >= 2


@pytest.mark.asyncio
async def test_http_sleep(client: AsyncClient) -> None:
    """GET /api/dashboard/sleep returns a trend response."""
    r = await client.get(
        "/api/dashboard/sleep",
        params={"start": "2026-06-01", "end": "2026-06-10", "granularity": "day"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["metric_label"] == "Sleep"
    assert data["metric_unit"] == "hours"
    assert len(data["series"]) == 10


@pytest.mark.asyncio
async def test_http_capabilities(client: AsyncClient) -> None:
    """GET /api/dashboard/capabilities returns named capability flags."""
    r = await client.get("/api/dashboard/capabilities")
    assert r.status_code == 200
    data = r.json()
    caps = {c["name"]: c["present"] for c in data["capabilities"]}
    assert caps["resting_hr"] is True
    assert caps["steps"] is True
    assert caps["sleep"] is True
    assert caps["hrv"] is True
    assert caps["workouts"] is True
