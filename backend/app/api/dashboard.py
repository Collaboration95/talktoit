"""Dashboard API routes — non-chat health data panels."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.analytics.metric_catalog import METRIC_CATALOG
from app.analytics.registry import (
    execute_activity_summary,
    execute_metric_trend,
    execute_workout_collection,
)
from app.db.aggregations import (
    DEFAULT_TZ,
    bucket_key,
    generate_buckets,
    to_local_dt,
    utc_bounds,
)
from app.db.connection import connect
from app.db.data_profile import get_data_profile
from app.db.migrate import table_has_column
from app.ingest.gpx import parse_gpx_route
from app.models.dashboard import (
    ActivityRingDay,
    ActivitySummaryResponse,
    CapabilitiesResponse,
    CapabilityFlag,
    DashboardResource,
    KeyValuePair,
    SleepStagesResponse,
    TrendPoint,
    TrendResponse,
    WorkoutDetail,
    WorkoutRouteState,
    WorkoutsResponse,
    WorkoutSummary,
)
from app.state.app_state import AppStateRepository
from app.state.diagnostics import safe_record

router = APIRouter(prefix="/api/dashboard")

# ---------------------------------------------------------------------------
# SQL constants (no f-strings in execute calls — avoids S608)
# ---------------------------------------------------------------------------

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
SELECT w.id, w.activity_type, w.start_date, w.duration, w.duration_unit, w.source_name,
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
  AND (? IS NULL OR w.activity_type = ?)
  AND (? IS NULL OR w.source_name = ?)
  AND (? IS NULL OR (w.start_date, w.id) < (?, ?))
ORDER BY w.start_date DESC, w.id DESC
LIMIT ?
"""
)

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

_SQL_CAPABILITIES_RECORD_HEALTH = """
SELECT type, COUNT(*) AS row_count, COUNT(value) AS numeric_count, COUNT(text_value) AS text_count
FROM records
GROUP BY type
"""

_SQL_CAPABILITIES_RECORDS_IN_WINDOW = """
SELECT DISTINCT type FROM records
WHERE start_date >= ? AND start_date < ?
"""

_SQL_CAPABILITIES_RECORD_HEALTH_IN_WINDOW = """
SELECT type, COUNT(*) AS row_count, COUNT(value) AS numeric_count, COUNT(text_value) AS text_count
FROM records
WHERE start_date >= ? AND start_date < ?
GROUP BY type
"""

# Variants for databases that predate typed category values (no text_value
# column yet). Numeric health stays measurable; category text counts are 0.
_SQL_CAPABILITIES_RECORD_HEALTH_LEGACY = """
SELECT type, COUNT(*) AS row_count, COUNT(value) AS numeric_count,
    COUNT(NULL) AS text_count
FROM records
GROUP BY type
"""

_SQL_CAPABILITIES_RECORD_HEALTH_IN_WINDOW_LEGACY = """
SELECT type, COUNT(*) AS row_count, COUNT(value) AS numeric_count,
    COUNT(NULL) AS text_count
FROM records
WHERE start_date >= ? AND start_date < ?
GROUP BY type
"""

_SQL_CAPABILITIES_WORKOUTS = """
SELECT COUNT(*) FROM workouts
"""

_SQL_CAPABILITIES_ACTIVITY_SUMMARIES = """
SELECT COUNT(*) FROM activity_summaries
"""

_SQL_CAPABILITIES_WORKOUTS_IN_WINDOW = """
SELECT COUNT(*) FROM workouts
WHERE start_date >= ? AND start_date < ?
"""

_SQL_CAPABILITIES_ACTIVITY_SUMMARIES_IN_WINDOW = """
SELECT COUNT(*) FROM activity_summaries
WHERE date_components >= ? AND date_components <= ?
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


def _workout_fingerprint(
    activity_type: str, start_date: datetime, duration: float | None, source_name: str
) -> str:
    """Return a stable local identity supplementing rebuild-local workout IDs."""
    raw = "|".join((activity_type, start_date.isoformat(), str(duration or ""), source_name))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _resource_metadata(
    conn: duckdb.DuckDBPyConnection,
    start_date: date | None,
    end_date: date | None,
    started_at: float,
    has_data: bool,
    panel: str,
) -> DashboardResource:
    """Build safe panel metadata without exposing local health observations."""
    profile = get_data_profile(conn)
    active = AppStateRepository().get_active()
    state = "success" if has_data else "empty"
    duration_ms = round((time.perf_counter() - started_at) * 1000)
    safe_record(
        None,
        "panel",
        f"panel:{panel}",
        duration_ms=duration_ms,
        status=state,
        meta={"panel_name": panel, "state": state},
    )
    return DashboardResource(
        state=state,
        dataset_version_id=active.id if active else None,
        effective_start=start_date.isoformat() if start_date else None,
        effective_end=end_date.isoformat() if end_date else None,
        coverage_start=profile.first_date.isoformat() if profile.first_date else None,
        coverage_end=profile.latest_date.isoformat() if profile.latest_date else None,
        generated_at=datetime.now(UTC).isoformat(),
        duration_ms=duration_ms,
    )


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
    started_at = time.perf_counter()
    start_date, end_date = _resolve_window(conn, start, end, days=7)

    rows = execute_activity_summary(conn, {"start": start_date, "end": end_date})

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
    return ActivitySummaryResponse(
        days=days,
        resource=_resource_metadata(conn, start_date, end_date, started_at, bool(days), "summary"),
    )


@router.get("/workouts", response_model=WorkoutsResponse)
def get_workouts(
    start: date | None = None,
    end: date | None = None,
    activity_type_filter: Annotated[
        str | None, Query(alias="activity_type", min_length=1, max_length=160)
    ] = None,
    source: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    cursor: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> WorkoutsResponse:
    """Return workouts for a date range (default: latest 30 local-data days)."""
    started_at = time.perf_counter()
    start_date, end_date = _resolve_window(conn, start, end, days=30)

    try:
        rows = execute_workout_collection(
            conn,
            {
                "start": start_date,
                "end": end_date,
                "activity_type": activity_type_filter,
                "source": source,
                "cursor": cursor,
                "limit": limit,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    workouts = []
    for row in rows[:limit]:
        (
            workout_id,
            activity_type,
            start_date_utc,
            duration,
            duration_unit,
            source_name,
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
                source_name=source_name,
                fingerprint=_workout_fingerprint(
                    activity_type, start_date_utc, duration, source_name
                ),
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
        resource=_resource_metadata(
            conn, start_date, end_date, started_at, bool(workouts), "workouts"
        ),
    )


@router.get("/steps", response_model=TrendResponse)
def get_steps(
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily step count trend (default: latest 30 local-data days)."""
    started_at = time.perf_counter()
    start_date, end_date = _resolve_window(conn, start, end, days=30)
    response = _build_trend(
        conn, "HKQuantityTypeIdentifierStepCount", granularity, start_date, end_date, "sum"
    )
    response.resource = _resource_metadata(
        conn,
        start_date,
        end_date,
        started_at,
        any(point.value is not None for point in response.series),
        "steps",
    )
    return response


@router.get("/heart", response_model=TrendResponse)
def get_heart(
    granularity: str = Query(default="week", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return weekly resting HR trend (default: latest 90 local-data days)."""
    started_at = time.perf_counter()
    start_date, end_date = _resolve_window(conn, start, end, days=90)
    response = _build_trend(
        conn, "HKQuantityTypeIdentifierRestingHeartRate", granularity, start_date, end_date, "avg"
    )
    response.resource = _resource_metadata(
        conn,
        start_date,
        end_date,
        started_at,
        any(point.value is not None for point in response.series),
        "heart",
    )
    return response


@router.get("/sleep", response_model=TrendResponse)
def get_sleep(
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> TrendResponse:
    """Return daily sleep duration trend (default: latest 30 local-data days)."""
    started_at = time.perf_counter()
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
        resource=_resource_metadata(
            conn, start_date, end_date, started_at, bool(bucket_sums), "sleep"
        ),
    )


@router.get("/sleep/stages", response_model=SleepStagesResponse)
def get_sleep_stages(
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> SleepStagesResponse:
    """Return local measured sleep stage durations without summing overlaps."""
    started_at = time.perf_counter()
    start_date, end_date = _resolve_window(conn, start, end, days=30)
    utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
    try:
        rows = conn.execute(_SQL_SLEEP_STAGE_RECORDS, [utc_start, utc_end]).fetchall()
    except duckdb.BinderException:
        # Imports that predate typed category values cannot supply stage
        # labels; fall through to the existing no-labels response below.
        rows = []
    intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    asleep: list[tuple[datetime, datetime]] = []
    for start_dt, end_dt, text_value in rows:
        if start_dt is None or end_dt is None:
            continue
        label = str(text_value or "")
        if "Asleep" not in label:
            continue
        interval = (start_dt, end_dt)
        # The total is the compatible union of every measured asleep interval,
        # including stage-less observations.  Stage rows are only a partition
        # when the source actually supplies a recognized stage label.
        asleep.append(interval)
        for stage in ("Core", "Deep", "REM"):
            if label.endswith(stage):
                intervals.setdefault(stage.lower(), []).append(interval)
    total_asleep_hours = round(_union_interval_hours(asleep), 2)
    stages = {stage: round(_union_interval_hours(values), 2) for stage, values in intervals.items()}
    if not stages:
        return SleepStagesResponse(
            total_asleep_hours=total_asleep_hours,
            stages_hours={},
            stage_data_available=False,
            message="Sleep stage labels are not available in this imported data.",
            resource=_resource_metadata(
                conn, start_date, end_date, started_at, bool(asleep), "sleep_stages"
            ),
        )
    if sum(stages.values()) > total_asleep_hours:
        return SleepStagesResponse(
            total_asleep_hours=total_asleep_hours,
            stages_hours={},
            stage_data_available=False,
            message=(
                "Sleep stage intervals overlap, so this import cannot provide a safe "
                "stage-duration partition."
            ),
            resource=_resource_metadata(
                conn, start_date, end_date, started_at, bool(asleep), "sleep_stages"
            ),
        )
    return SleepStagesResponse(
        total_asleep_hours=total_asleep_hours,
        stages_hours=stages,
        stage_data_available=True,
        message=(
            "Stage durations are measured source observations; overlapping intervals are unioned "
            "locally."
        ),
        resource=_resource_metadata(conn, start_date, end_date, started_at, True, "sleep_stages"),
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(
    start: date | None = None,
    end: date | None = None,
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> CapabilitiesResponse:
    """Return catalog availability, including the requested dashboard range."""
    started_at = time.perf_counter()
    rows = conn.execute(_SQL_CAPABILITIES_RECORDS).fetchall()
    present_types = {row[0] for row in rows}
    text_values_available = table_has_column(conn, "records", "text_value")
    record_health = {
        row[0]: {"rows": row[1], "numeric": row[2], "text": row[3]}
        for row in conn.execute(
            _SQL_CAPABILITIES_RECORD_HEALTH
            if text_values_available
            else _SQL_CAPABILITIES_RECORD_HEALTH_LEGACY
        ).fetchall()
    }

    counts = {
        "workouts": (conn.execute(_SQL_CAPABILITIES_WORKOUTS).fetchone() or [0])[0],
        "activity_summaries": (
            conn.execute(_SQL_CAPABILITIES_ACTIVITY_SUMMARIES).fetchone() or [0]
        )[0],
    }
    resource_start: date | None = None
    resource_end: date | None = None

    if start is not None or end is not None:
        start_date, end_date = _resolve_window(conn, start, end, days=30)
        resource_start, resource_end = start_date, end_date
        utc_start, utc_end = utc_bounds(start_date, end_date, DEFAULT_TZ)
        scoped_record_types = {
            row[0]
            for row in conn.execute(
                _SQL_CAPABILITIES_RECORDS_IN_WINDOW, [utc_start, utc_end]
            ).fetchall()
        }
        scoped_record_health = {
            row[0]: {"rows": row[1], "numeric": row[2], "text": row[3]}
            for row in conn.execute(
                _SQL_CAPABILITIES_RECORD_HEALTH_IN_WINDOW
                if text_values_available
                else _SQL_CAPABILITIES_RECORD_HEALTH_IN_WINDOW_LEGACY,
                [utc_start, utc_end],
            ).fetchall()
        }
        scoped_counts = {
            "workouts": (
                conn.execute(_SQL_CAPABILITIES_WORKOUTS_IN_WINDOW, [utc_start, utc_end]).fetchone()
                or [0]
            )[0],
            "activity_summaries": (
                conn.execute(
                    _SQL_CAPABILITIES_ACTIVITY_SUMMARIES_IN_WINDOW,
                    [start_date.isoformat(), end_date.isoformat()],
                ).fetchone()
                or [0]
            )[0],
        }
    else:
        scoped_record_types = present_types
        scoped_record_health = record_health
        scoped_counts = counts

    def availability(
        metric_id: str,
    ) -> tuple[
        bool, Literal["available", "unavailable", "out_of_range", "malformed", "unsupported"]
    ]:
        metric = METRIC_CATALOG[metric_id]
        if metric.availability_source == "records":
            matching_types = set(metric.apple_types).intersection(present_types)
            globally_present = bool(matching_types)
            scoped_present = bool(set(metric.apple_types).intersection(scoped_record_types))
            required_value = "text" if metric.value_kind == "category" else "numeric"
            globally_valid = any(record_health[item][required_value] > 0 for item in matching_types)
            scoped_valid = any(
                scoped_record_health[item][required_value] > 0
                for item in set(metric.apple_types).intersection(scoped_record_types)
            )
        else:
            globally_present = counts[metric.availability_source] > 0
            scoped_present = scoped_counts[metric.availability_source] > 0
            globally_valid = globally_present
            scoped_valid = scoped_present
        if not globally_present:
            return False, "unavailable"
        if not globally_valid:
            return False, "malformed"
        if not scoped_present or not scoped_valid:
            return False, "out_of_range"
        return True, "available"

    capabilities = [
        CapabilityFlag(name=metric.id, present=present, state=state)
        for metric in METRIC_CATALOG.values()
        for present, state in [availability(metric.id)]
    ]
    return CapabilitiesResponse(
        capabilities=capabilities,
        resource=_resource_metadata(
            conn,
            resource_start,
            resource_end,
            started_at,
            any(item.present for item in capabilities),
            "capabilities",
        ),
    )


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
    chart = execute_metric_trend(
        conn,
        {
            "metric_id": metric_id,
            "granularity": granularity,
            "start": start_date,
            "end": end_date,
            "aggregation": agg,
        },
    )
    return TrendResponse(
        metric_label=chart.metric_label,
        metric_unit=chart.metric_unit,
        granularity=chart.granularity,
        series=[TrendPoint(bucket=point.bucket, value=point.value) for point in chart.series],
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
    fingerprint: str | None = Query(default=None, pattern="^[a-f0-9]{16}$"),
    conn: duckdb.DuckDBPyConnection = Depends(_get_conn),  # noqa: B008
) -> WorkoutDetail:
    """Return full detail for a single workout, including GPS and metadata."""
    started_at = time.perf_counter()
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
    canonical_fingerprint = _workout_fingerprint(
        activity_type, start_date_utc, duration, source_name
    )
    if fingerprint is not None and fingerprint != canonical_fingerprint:
        raise HTTPException(status_code=404, detail="Workout link no longer matches this dataset")
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
        fingerprint=canonical_fingerprint,
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
        resource=_resource_metadata(conn, None, None, started_at, True, "workout_detail"),
    )
