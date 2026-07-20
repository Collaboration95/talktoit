"""Dashboard API routes — non-chat health data panels."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.analytics.metric_catalog import METRIC_CATALOG
from app.db.aggregations import (
    DEFAULT_TZ,
    METRIC_META,
    bucket_key,
    generate_buckets,
    to_local_dt,
    utc_bounds,
)
from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.ingest.gpx import parse_gpx_route
from app.models.dashboard import (
    ActivityRingDay,
    ActivitySummaryResponse,
    CapabilitiesResponse,
    CapabilityFlag,
    KeyValuePair,
    SleepStagesResponse,
    TrendPoint,
    TrendResponse,
    WorkoutDetail,
    WorkoutRouteState,
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

_SQL_DISTANCE_STATS = """
SELECT workout_id,
    SUM(CASE
        WHEN LOWER(unit) = 'km' THEN sum * 1000.0
        WHEN LOWER(unit) IN ('mi', 'mile', 'miles') THEN sum * 1609.344
        ELSE sum
    END) AS distance_m
FROM workout_statistics
WHERE type IN ('HKQuantityTypeIdentifierDistanceWalkingRunning',
               'HKQuantityTypeIdentifierDistanceCycling',
               'HKQuantityTypeIdentifierDistanceSwimming')
GROUP BY workout_id
"""

_SQL_WORKOUTS_LIST = (
    """
SELECT w.id, w.activity_type, w.start_date, w.duration, w.duration_unit,
    hr.average AS avg_hr,
    dist.distance_m AS distance_m,
    energy.sum AS energy_kj
FROM workouts w
LEFT JOIN workout_statistics hr
    ON hr.workout_id = w.id
    AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
LEFT JOIN (
"""
    + _SQL_DISTANCE_STATS
    + """
) dist ON dist.workout_id = w.id
LEFT JOIN workout_statistics energy
    ON energy.workout_id = w.id
    AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
WHERE w.start_date >= ? AND w.start_date < ?
  AND (? IS NULL OR (w.start_date, w.id) < (?, ?))
ORDER BY w.start_date DESC, w.id DESC
LIMIT ?
"""
)

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

_SQL_SLEEP_STAGE_RECORDS = """
SELECT start_date, end_date, text_value
FROM records
WHERE type = 'HKCategoryTypeIdentifierSleepAnalysis'
  AND start_date >= ? AND start_date < ?
ORDER BY start_date
"""

_SQL_CAPABILITIES_RECORDS = "SELECT DISTINCT type FROM records"

_SQL_CAPABILITIES_WORKOUTS = """
SELECT COUNT(*) FROM workouts
"""

_SQL_WORKOUT_DETAIL = (
    """
SELECT
    w.id,
    w.activity_type,
    w.start_date,
    w.duration,
    w.duration_unit,
    w.source_name,
    hr.average          AS avg_hr,
    hr.maximum          AS max_hr,
    dist.distance_m     AS distance_m,
    energy.sum          AS energy_kj,
    TRY_CAST(elev.value AS DOUBLE) AS elevation_m
FROM workouts w
LEFT JOIN workout_statistics hr
    ON hr.workout_id = w.id
    AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
LEFT JOIN (
"""
    + _SQL_DISTANCE_STATS
    + """
) dist ON dist.workout_id = w.id
LEFT JOIN workout_statistics energy
    ON energy.workout_id = w.id
    AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
LEFT JOIN workout_metadata elev
    ON elev.workout_id = w.id
    AND elev.key = 'HKElevationAscended'
WHERE w.id = ?
"""
)

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
    conn = connect(read_only=True)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_window(
    conn: duckdb.DuckDBPyConnection,
    start: date | None,
    end: date | None,
    days: int,
) -> tuple[date, date]:
    """Resolve a date range against the last day present in local data.

    An Apple Health export is a snapshot, so using the computer clock creates
    empty future buckets after an export becomes stale. Explicit dates still
    take precedence for API consumers and tests.
    """
    end_date = end or get_data_profile(conn).latest_date
    end_date = end_date or date.today()
    start_date = start or end_date - timedelta(days=days - 1)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must not be after end")
    return start_date, end_date


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
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> ActivitySummaryResponse:
    """Return activity ring data for a date range (default: last 7 days)."""
    start_date, end_date = _resolve_window(conn, start, end, days=7)

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
    start: date | None = None,
    end: date | None = None,
    cursor: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> WorkoutsResponse:
    """Return workouts for a date range (default: latest 30 local-data days)."""
    start_date, end_date = _resolve_window(conn, start, end, days=30)

    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    cursor_date: datetime | None = None
    cursor_id: int | None = None
    if cursor is not None:
        try:
            date_text, id_text = cursor.rsplit("|", maxsplit=1)
            cursor_date = datetime.fromisoformat(date_text)
            cursor_id = int(id_text)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid workout cursor") from exc
    rows = conn.execute(
        _SQL_WORKOUTS_LIST,
        [utc_start, utc_end, cursor_date, cursor_date, cursor_id, limit + 1],
    ).fetchall()

    workouts = []
    for row in rows[:limit]:
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
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = f"{last[2].isoformat()}|{last[0]}"
    return WorkoutsResponse(
        workouts=workouts,
        next_cursor=next_cursor,
        effective_start=start_date.isoformat(),
        effective_end=end_date.isoformat(),
    )


@router.get("/steps", response_model=TrendResponse)
def get_steps(
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily step count trend (default: latest 30 local-data days)."""
    start_date, end_date = _resolve_window(conn, start, end, days=30)
    return _build_trend(
        conn, "HKQuantityTypeIdentifierStepCount", granularity, start_date, end_date, "sum"
    )


@router.get("/heart", response_model=TrendResponse)
def get_heart(
    granularity: str = Query(default="week", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return weekly resting HR trend (default: latest 90 local-data days)."""
    start_date, end_date = _resolve_window(conn, start, end, days=90)
    return _build_trend(
        conn, "HKQuantityTypeIdentifierRestingHeartRate", granularity, start_date, end_date, "avg"
    )


@router.get("/sleep", response_model=TrendResponse)
def get_sleep(
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily sleep duration trend (default: latest 30 local-data days)."""
    start_date, end_date = _resolve_window(conn, start, end, days=30)

    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    rows = conn.execute(_SQL_SLEEP_RECORDS, [utc_start, utc_end]).fetchall()

    # Apple Health commonly stores overlapping in-bed, awake, and stage
    # intervals.  The raw category value is not persisted, so sum-of-rows
    # double-counts sleep. Merge intervals instead to report elapsed time.
    bucket_intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    for start_dt_utc, end_dt_utc in rows:
        local_dt = to_local_dt(start_dt_utc, DEFAULT_TZ)
        key = bucket_key(local_dt.date(), granularity)  # type: ignore[arg-type]
        bucket_intervals.setdefault(key, []).append(
            (to_local_dt(start_dt_utc, DEFAULT_TZ), to_local_dt(end_dt_utc, DEFAULT_TZ))
        )

    bucket_sums: dict[str, float] = {}
    for key, intervals in bucket_intervals.items():
        merged: list[list[datetime]] = []
        for interval_start, interval_end in sorted(intervals):
            if not merged or interval_start > merged[-1][1]:
                merged.append([interval_start, interval_end])
            elif interval_end > merged[-1][1]:
                merged[-1][1] = interval_end
        bucket_sums[key] = sum(
            (interval_end - interval_start).total_seconds() / 3600.0
            for interval_start, interval_end in merged
        )

    all_buckets = generate_buckets(start_date, end_date, granularity)  # type: ignore[arg-type]
    series = [TrendPoint(bucket=b, value=bucket_sums.get(b)) for b in all_buckets]

    return TrendResponse(
        metric_label="Sleep",
        metric_unit="hours",
        granularity=granularity,
        series=series,
    )


@router.get("/sleep/stages", response_model=SleepStagesResponse)
def get_sleep_stages(
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> SleepStagesResponse:
    """Return local measured sleep stage durations without summing overlaps."""
    start_date, end_date = _resolve_window(conn, start, end, days=30)
    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    rows = conn.execute(_SQL_SLEEP_STAGE_RECORDS, [utc_start, utc_end]).fetchall()
    intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    asleep: list[tuple[datetime, datetime]] = []
    for start_dt, end_dt, text_value in rows:
        if start_dt is None or end_dt is None:
            continue
        label = str(text_value or "")
        if "Asleep" not in label:
            continue
        interval = (start_dt, end_dt)
        asleep.append(interval)
        for stage in ("Core", "Deep", "REM"):
            if label.endswith(stage):
                intervals.setdefault(stage.lower(), []).append(interval)
    stages = {stage: round(_union_interval_hours(values), 2) for stage, values in intervals.items()}
    if not stages:
        return SleepStagesResponse(
            total_asleep_hours=round(_union_interval_hours(asleep), 2),
            stages_hours={},
            stage_data_available=False,
            message="Sleep stage labels are not available in this imported data.",
        )
    return SleepStagesResponse(
        total_asleep_hours=round(_union_interval_hours(asleep), 2),
        stages_hours=stages,
        stage_data_available=True,
        message=(
            "Stage durations are measured source observations; overlapping intervals are unioned "
            "locally."
        ),
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> CapabilitiesResponse:
    """Return which data sources are present in the export."""
    rows = conn.execute(_SQL_CAPABILITIES_RECORDS).fetchall()
    present_types = {row[0] for row in rows}

    workout_count_row = conn.execute(_SQL_CAPABILITIES_WORKOUTS).fetchone()
    has_workouts = (workout_count_row[0] > 0) if workout_count_row else False

    capabilities = [
        CapabilityFlag(
            name=metric.id,
            present=bool(set(metric.apple_types).intersection(present_types)),
        )
        for metric in METRIC_CATALOG.values()
        if metric.apple_types
    ] + [
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


def _union_interval_hours(intervals: list[tuple[datetime, datetime]]) -> float:
    """Return elapsed hours for intervals after merging compatible overlaps."""
    merged: list[list[datetime]] = []
    for interval_start, interval_end in sorted(intervals):
        if not merged or interval_start > merged[-1][1]:
            merged.append([interval_start, interval_end])
        elif interval_end > merged[-1][1]:
            merged[-1][1] = interval_end
    return sum((end - start).total_seconds() / 3600.0 for start, end in merged)


# ---------------------------------------------------------------------------
# Workout detail (R1-01)
# ---------------------------------------------------------------------------


@router.get("/workouts/{workout_id}", response_model=WorkoutDetail)
def get_workout_detail(
    workout_id: int = Path(ge=1),
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
    route = WorkoutRouteState(state="missing", message="No route is available for this workout.")
    route_path_row = conn.execute(_SQL_WORKOUT_ROUTE_PATH, [workout_id]).fetchone()
    if route_path_row is not None and route_path_row[0] is not None:
        gps_route = parse_gpx_route(route_path_row[0])
        if gps_route is None:
            route = WorkoutRouteState(state="invalid", message="The saved route could not be read.")
        else:
            route = WorkoutRouteState(state="available", message="Route data is available.")

    return WorkoutDetail(
        id=wid,
        activity_type=activity_type,
        date=local_dt.isoformat(),
        duration_minutes=duration_minutes,
        avg_heart_rate=avg_heart_rate,
        max_heart_rate=max_heart_rate,
        distance_meters=distance_m,
        distance_unit="m",
        energy_burned_kj=energy_kj,
        elevation_ascent_meters=elevation_m,
        source_name=source_name,
        gps_route=gps_route,
        metadata=metadata,
        route=route,
    )
