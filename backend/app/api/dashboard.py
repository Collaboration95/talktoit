"""Dashboard API routes — non-chat health data panels."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from app.db.aggregations import (
    DEFAULT_TZ,
    METRIC_META,
    bucket_key,
    generate_buckets,
    to_local_dt,
    utc_bounds,
)
from app.db.connection import connect
from app.ingest.gpx import parse_gpx_route
from app.models.dashboard import (
    ActivityRingDay,
    ActivitySummaryResponse,
    CapabilitiesResponse,
    CapabilityFlag,
    KeyValuePair,
    TrendPoint,
    TrendResponse,
    WorkoutDetail,
    WorkoutsResponse,
    WorkoutSummary,
)

if TYPE_CHECKING:
    import duckdb

router = APIRouter(prefix="/api/dashboard")

# ---------------------------------------------------------------------------
# SQL constants (no f-strings in execute calls — avoids S608)
# ---------------------------------------------------------------------------

_SQL_ACTIVITY_SUMMARY = """
SELECT date_components, active_energy_burned, active_energy_burned_goal,
       apple_exercise_time, apple_exercise_time_goal,
       apple_stand_hours, apple_stand_hours_goal
FROM activity_summaries
WHERE date_components >= ? AND date_components <= ?
ORDER BY date_components DESC
"""

_SQL_WORKOUTS_LIST = """
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
"""

_SQL_TREND_RECORDS = """
SELECT start_date, value
FROM records
WHERE type = ?
  AND start_date >= ?
  AND start_date < ?
  AND value IS NOT NULL
ORDER BY start_date
"""

_SQL_SLEEP_RECORDS = """
SELECT start_date, end_date
FROM records
WHERE type = 'HKCategoryTypeIdentifierSleepAnalysis'
  AND source_name != 'AutoSleep'
  AND start_date >= ? AND start_date < ?
ORDER BY start_date
"""

_SQL_CAPABILITIES_RECORDS = """
SELECT type, COUNT(*) AS cnt FROM records
WHERE type IN ('HKQuantityTypeIdentifierRestingHeartRate',
               'HKQuantityTypeIdentifierStepCount',
               'HKCategoryTypeIdentifierSleepAnalysis',
               'HKQuantityTypeIdentifierHeartRateVariabilitySDNN')
GROUP BY type
"""

_SQL_CAPABILITIES_WORKOUTS = """
SELECT COUNT(*) FROM workouts
"""

_SQL_WORKOUT_DETAIL = """
SELECT
    w.id,
    w.activity_type,
    w.start_date,
    w.duration,
    w.duration_unit,
    w.source_name,
    hr.average          AS avg_hr,
    hr.maximum          AS max_hr,
    dist.sum            AS distance_m,
    energy.sum          AS energy_kj,
    TRY_CAST(elev.value AS DOUBLE) AS elevation_m
FROM workouts w
LEFT JOIN workout_statistics hr
    ON hr.workout_id = w.id
    AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
LEFT JOIN (
    SELECT workout_id, sum
    FROM workout_statistics
    WHERE type IN (
        'HKQuantityTypeIdentifierDistanceWalkingRunning',
        'HKQuantityTypeIdentifierDistanceCycling',
        'HKQuantityTypeIdentifierDistanceSwimming'
    )
) dist ON dist.workout_id = w.id
LEFT JOIN workout_statistics energy
    ON energy.workout_id = w.id
    AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
LEFT JOIN workout_metadata elev
    ON elev.workout_id = w.id
    AND elev.key = 'HKElevationAscended'
WHERE w.id = ?
"""

_SQL_WORKOUT_METADATA = """
SELECT key, value
FROM workout_metadata
WHERE workout_id = ?
"""

_SQL_WORKOUT_ROUTE_PATH = """
SELECT file_path
FROM workout_routes
WHERE workout_id = ?
LIMIT 1
"""

# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _get_conn() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """FastAPI dependency — open a DB connection for the request lifetime."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_start(days_back: int) -> date:
    return date.today() - timedelta(days=days_back)


def _default_end() -> date:
    return date.today()


def _duration_minutes(duration: float | None, unit: str | None) -> float | None:
    if duration is None:
        return None
    if unit == "hr":
        return duration * 60.0
    return float(duration)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=ActivitySummaryResponse)
def get_summary(
    start: str | None = None,
    end: str | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> ActivitySummaryResponse:
    """Return activity ring data for a date range (default: last 7 days)."""
    start_date = date.fromisoformat(start) if start else _default_start(6)
    end_date = date.fromisoformat(end) if end else _default_end()

    rows = conn.execute(
        _SQL_ACTIVITY_SUMMARY, [start_date.isoformat(), end_date.isoformat()]
    ).fetchall()

    days = [
        ActivityRingDay(
            date=row[0],
            energy_kj=row[1],
            energy_goal_kj=row[2],
            exercise_min=row[3],
            exercise_goal_min=row[4],
            stand_hours=row[5],
            stand_goal_hours=row[6],
        )
        for row in rows
    ]
    return ActivitySummaryResponse(days=days)


@router.get("/workouts", response_model=WorkoutsResponse)
def get_workouts(
    start: str | None = None,
    end: str | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> WorkoutsResponse:
    """Return workouts for a date range (default: last 30 days)."""
    start_date = date.fromisoformat(start) if start else _default_start(30)
    end_date = date.fromisoformat(end) if end else _default_end()

    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    rows = conn.execute(_SQL_WORKOUTS_LIST, [utc_start, utc_end]).fetchall()

    workouts = []
    for row in rows:
        (
            workout_id,
            activity_type,
            start_date_utc,
            duration,
            duration_unit,
            avg_hr,
            distance_m,
            energy_kj,
        ) = row
        local_dt = to_local_dt(start_date_utc, DEFAULT_TZ)
        avg_hr_int = round(avg_hr) if avg_hr is not None else None
        workouts.append(
            WorkoutSummary(
                id=workout_id,
                activity_type=activity_type,
                date=local_dt.isoformat(),
                duration_minutes=_duration_minutes(duration, duration_unit),
                avg_heart_rate=avg_hr_int,
                distance_meters=distance_m,
                energy_burned_kj=energy_kj,
            )
        )
    return WorkoutsResponse(workouts=workouts)


@router.get("/steps", response_model=TrendResponse)
def get_steps(
    granularity: str = "day",
    start: str | None = None,
    end: str | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily step count trend (default: last 30 days)."""
    start_date = date.fromisoformat(start) if start else _default_start(30)
    end_date = date.fromisoformat(end) if end else _default_end()
    return _build_trend(
        conn, "HKQuantityTypeIdentifierStepCount", granularity, start_date, end_date, "sum"
    )


@router.get("/heart", response_model=TrendResponse)
def get_heart(
    granularity: str = "week",
    start: str | None = None,
    end: str | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return weekly resting HR trend (default: last 90 days)."""
    start_date = date.fromisoformat(start) if start else _default_start(90)
    end_date = date.fromisoformat(end) if end else _default_end()
    return _build_trend(
        conn, "HKQuantityTypeIdentifierRestingHeartRate", granularity, start_date, end_date, "avg"
    )


@router.get("/sleep", response_model=TrendResponse)
def get_sleep(
    granularity: str = "day",
    start: str | None = None,
    end: str | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily sleep duration trend (default: last 30 days)."""
    start_date = date.fromisoformat(start) if start else _default_start(30)
    end_date = date.fromisoformat(end) if end else _default_end()

    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    rows = conn.execute(_SQL_SLEEP_RECORDS, [utc_start, utc_end]).fetchall()

    bucket_sums: dict[str, float] = {}
    for start_dt_utc, end_dt_utc in rows:
        duration_hours = (end_dt_utc - start_dt_utc).total_seconds() / 3600.0
        local_dt = to_local_dt(start_dt_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), granularity)  # type: ignore[arg-type]
        bucket_sums[key] = bucket_sums.get(key, 0.0) + duration_hours

    all_buckets = generate_buckets(start_date, end_date, granularity)  # type: ignore[arg-type]
    series = [TrendPoint(bucket=b, value=bucket_sums.get(b)) for b in all_buckets]

    return TrendResponse(
        metric_label="Sleep",
        metric_unit="hours",
        granularity=granularity,
        series=series,
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> CapabilitiesResponse:
    """Return which data sources are present in the export."""
    rows = conn.execute(_SQL_CAPABILITIES_RECORDS).fetchall()
    present_types = {row[0] for row in rows if row[1] > 0}

    workout_count_row = conn.execute(_SQL_CAPABILITIES_WORKOUTS).fetchone()
    has_workouts = (workout_count_row[0] > 0) if workout_count_row else False

    resting_hr_type = "HKQuantityTypeIdentifierRestingHeartRate"
    steps_type = "HKQuantityTypeIdentifierStepCount"
    sleep_type = "HKCategoryTypeIdentifierSleepAnalysis"
    hrv_type = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"

    capabilities = [
        CapabilityFlag(name="resting_hr", present=resting_hr_type in present_types),
        CapabilityFlag(name="steps", present=steps_type in present_types),
        CapabilityFlag(name="sleep", present=sleep_type in present_types),
        CapabilityFlag(name="hrv", present=hrv_type in present_types),
        CapabilityFlag(name="workouts", present=has_workouts),
    ]
    return CapabilitiesResponse(capabilities=capabilities)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_trend(
    conn: duckdb.DuckDBPyConnection,
    metric_id: str,
    granularity: str,
    start_date: date,
    end_date: date,
    agg: str,
) -> TrendResponse:
    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    rows = conn.execute(_SQL_TREND_RECORDS, [metric_id, utc_start, utc_end]).fetchall()

    bucket_values: dict[str, list[float]] = {}
    for start_date_utc, value in rows:
        local_dt = to_local_dt(start_date_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), granularity)  # type: ignore[arg-type]
        bucket_values.setdefault(key, []).append(float(value))

    aggregated: dict[str, float] = {}
    for key, vals in bucket_values.items():
        if agg == "sum":
            aggregated[key] = sum(vals)
        else:
            aggregated[key] = sum(vals) / len(vals)

    all_buckets = generate_buckets(start_date, end_date, granularity)  # type: ignore[arg-type]
    series = [TrendPoint(bucket=b, value=aggregated.get(b)) for b in all_buckets]

    label, unit = METRIC_META.get(metric_id, (metric_id, ""))
    return TrendResponse(
        metric_label=label,
        metric_unit=unit,
        granularity=granularity,
        series=series,
    )


# ---------------------------------------------------------------------------
# Workout detail (R1-01)
# ---------------------------------------------------------------------------


@router.get("/workouts/{workout_id}", response_model=WorkoutDetail)
def get_workout_detail(
    workout_id: int,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> WorkoutDetail:
    """Return full detail for a single workout, including GPS and metadata."""
    row = conn.execute(_SQL_WORKOUT_DETAIL, [workout_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Workout not found")

    (
        wid,
        activity_type,
        start_date_utc,
        duration,
        duration_unit,
        source_name,
        avg_hr_raw,
        max_hr_raw,
        distance_m,
        energy_kj,
        elevation_m,
    ) = row

    local_dt = to_local_dt(start_date_utc, DEFAULT_TZ)
    duration_minutes = _duration_minutes(duration, duration_unit)
    avg_heart_rate = round(avg_hr_raw) if avg_hr_raw is not None else None
    max_heart_rate = round(max_hr_raw) if max_hr_raw is not None else None

    # Fetch metadata
    meta_rows = conn.execute(_SQL_WORKOUT_METADATA, [workout_id]).fetchall()
    metadata = [KeyValuePair(key=m[0], value=m[1]) for m in meta_rows]

    # Fetch GPS route if it exists
    gps_route = None
    route_path_row = conn.execute(_SQL_WORKOUT_ROUTE_PATH, [workout_id]).fetchone()
    if route_path_row is not None and route_path_row[0] is not None:
        gps_route = parse_gpx_route(route_path_row[0])

    return WorkoutDetail(
        id=wid,
        activity_type=activity_type,
        date=local_dt.isoformat(),
        duration_minutes=duration_minutes,
        avg_heart_rate=avg_heart_rate,
        max_heart_rate=max_heart_rate,
        distance_meters=distance_m,
        distance_unit="km",
        energy_burned_kj=energy_kj,
        elevation_ascent_meters=elevation_m,
        source_name=source_name,
        gps_route=gps_route,
        metadata=metadata,
    )
