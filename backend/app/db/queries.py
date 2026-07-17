"""Typed DuckDB query functions returning Pydantic models.

All public functions accept an open DuckDB connection and return typed model
instances from :mod:`app.models.templates`.  SQL is stored as module-level
constants; no f-strings appear in ``execute`` calls (S608).

Timestamps stored in DuckDB are UTC-naive (the ingestion pipeline converts
Apple Health's +0800 offsets to UTC before insert).  All date-filter helpers
therefore convert local dates to UTC bounds before querying.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from app.db.aggregations import (
    DEFAULT_TZ,
    METRIC_AGGREGATION,
    METRIC_META,
    bucket_key,
    compute_delta,
    compute_direction,
    generate_buckets,
    minutes_from_duration,
    to_local_dt,
    utc_bounds,
)
from app.models.templates import (
    ComparisonData,
    ComparisonMetric,
    FallbackData,
    FallbackTableRow,
    PeriodMetric,
    PeriodSummaryData,
    RankedListData,
    RankedListRow,
    TrendChartData,
    TrendPoint,
    WorkoutCardData,
)

if TYPE_CHECKING:
    import duckdb

# ---------------------------------------------------------------------------
# SQL constants (no f-strings in execute calls — avoids S608)
# ---------------------------------------------------------------------------

_SQL_LAST_WORKOUT = """
SELECT
    w.id,
    w.activity_type,
    w.start_date,
    w.duration,
    w.duration_unit,
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
    SELECT workout_id,
        SUM(CASE
            WHEN LOWER(unit) = 'km' THEN sum * 1000.0
            WHEN LOWER(unit) IN ('mi', 'mile', 'miles') THEN sum * 1609.344
            ELSE sum
        END) AS distance_m
    FROM workout_statistics
    WHERE type IN (
        'HKQuantityTypeIdentifierDistanceWalkingRunning',
        'HKQuantityTypeIdentifierDistanceCycling',
        'HKQuantityTypeIdentifierDistanceSwimming'
    )
    GROUP BY workout_id
) dist ON dist.workout_id = w.id
LEFT JOIN workout_statistics energy
    ON energy.workout_id = w.id
    AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
LEFT JOIN workout_metadata elev
    ON elev.workout_id = w.id
    AND elev.key = 'HKElevationAscended'
WHERE w.activity_type = ?
ORDER BY w.start_date DESC
LIMIT 1
"""

_SQL_TOP_WORKOUTS = """
SELECT
    w.id,
    w.activity_type,
    w.start_date,
    w.duration,
    w.duration_unit,
    hr.average   AS avg_hr,
    hr.maximum   AS max_hr,
    dist.distance_m AS distance_m,
    energy.sum   AS energy_kj
FROM workouts w
LEFT JOIN workout_statistics hr
    ON hr.workout_id = w.id
    AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
LEFT JOIN (
    SELECT workout_id,
        SUM(CASE
            WHEN LOWER(unit) = 'km' THEN sum * 1000.0
            WHEN LOWER(unit) IN ('mi', 'mile', 'miles') THEN sum * 1609.344
            ELSE sum
        END) AS distance_m
    FROM workout_statistics
    WHERE type IN (
        'HKQuantityTypeIdentifierDistanceWalkingRunning',
        'HKQuantityTypeIdentifierDistanceCycling',
        'HKQuantityTypeIdentifierDistanceSwimming'
    )
    GROUP BY workout_id
) dist ON dist.workout_id = w.id
LEFT JOIN workout_statistics energy
    ON energy.workout_id = w.id
    AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
WHERE w.activity_type = ?
  AND w.start_date >= ?
  AND w.start_date < ?
"""

_SQL_TREND = """
SELECT start_date, value
FROM records
WHERE type = ?
  AND start_date >= ?
  AND start_date < ?
  AND value IS NOT NULL
ORDER BY start_date
"""

_SQL_WORKOUTS_STATS = """
SELECT COUNT(*) AS cnt, SUM(duration) AS dur
FROM workouts
WHERE start_date >= ? AND start_date < ?
"""

_SQL_DISTANCE = """
SELECT SUM(CASE
    WHEN LOWER(ws.unit) = 'km' THEN ws.sum * 1000.0
    WHEN LOWER(ws.unit) IN ('mi', 'mile', 'miles') THEN ws.sum * 1609.344
    ELSE ws.sum
END)
FROM workout_statistics ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.type IN (
    'HKQuantityTypeIdentifierDistanceWalkingRunning',
    'HKQuantityTypeIdentifierDistanceCycling',
    'HKQuantityTypeIdentifierDistanceSwimming'
)
AND w.start_date >= ? AND w.start_date < ?
"""

_SQL_ENERGY = """
SELECT SUM(ws.sum)
FROM workout_statistics ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
AND w.start_date >= ? AND w.start_date < ?
"""

_SQL_WORKOUTS_STATS_FILTERED = """
SELECT COUNT(*) AS cnt, SUM(w.duration) AS dur
FROM workouts w
WHERE w.start_date >= ? AND w.start_date < ? AND w.activity_type = ?
"""

_SQL_DISTANCE_FILTERED = """
SELECT SUM(CASE
    WHEN LOWER(ws.unit) = 'km' THEN ws.sum * 1000.0
    WHEN LOWER(ws.unit) IN ('mi', 'mile', 'miles') THEN ws.sum * 1609.344
    ELSE ws.sum
END)
FROM workout_statistics ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.type IN (
    'HKQuantityTypeIdentifierDistanceWalkingRunning',
    'HKQuantityTypeIdentifierDistanceCycling',
    'HKQuantityTypeIdentifierDistanceSwimming'
)
AND w.start_date >= ? AND w.start_date < ? AND w.activity_type = ?
"""

_SQL_ENERGY_FILTERED = """
SELECT SUM(ws.sum)
FROM workout_statistics ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
AND w.start_date >= ? AND w.start_date < ? AND w.activity_type = ?
"""

# ---------------------------------------------------------------------------
# Private aliases for backward compat within this module
# ---------------------------------------------------------------------------

_utc_bounds = utc_bounds
_to_local_dt = to_local_dt


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------


def get_last_workout(
    conn: duckdb.DuckDBPyConnection,
    activity_type: str,
    tz: str = DEFAULT_TZ,
) -> WorkoutCardData | None:
    """Fetch the most recent workout of the given type.

    Args:
        conn: Open DuckDB connection.
        activity_type: Activity type string as stored in the DB (e.g. ``"Running"``).
        tz: IANA timezone for converting the UTC start_date to local time.

    Returns:
        A :class:`WorkoutCardData` for the most recent matching workout, or
        ``None`` if no workout of that type exists.
    """
    row = conn.execute(_SQL_LAST_WORKOUT, [activity_type]).fetchone()
    if row is None:
        return None

    (
        _workout_id,
        act_type,
        start_date_utc,
        duration,
        duration_unit,
        avg_hr_raw,
        max_hr_raw,
        distance_m,
        energy_kj,
        elevation_m,
    ) = row

    local_dt = _to_local_dt(start_date_utc, tz)
    duration_minutes = minutes_from_duration(duration, duration_unit) or 0.0
    avg_heart_rate = round(avg_hr_raw) if avg_hr_raw is not None else None
    max_heart_rate = round(max_hr_raw) if max_hr_raw is not None else None

    return WorkoutCardData(
        activity_type=act_type,
        date=local_dt,
        duration_minutes=duration_minutes,
        avg_heart_rate=avg_heart_rate,
        max_heart_rate=max_heart_rate,
        distance_meters=distance_m,
        distance_unit="m",
        energy_burned_kj=energy_kj,
        elevation_ascent_meters=elevation_m,
        gps_route=None,
    )


def get_top_workouts(
    conn: duckdb.DuckDBPyConnection,
    activity_type: str,
    metric: Literal["distance", "duration", "avg_hr", "energy"],
    n: int = 5,
    start: date | None = None,
    end: date | None = None,
    title: str | None = None,
    tz: str = DEFAULT_TZ,
) -> RankedListData:
    """Fetch the top N workouts of a given type ranked by a chosen metric.

    Args:
        conn: Open DuckDB connection.
        activity_type: Activity type string (e.g. ``"Running"``).
        metric: The ranking metric: ``"distance"``, ``"duration"``,
            ``"avg_hr"``, or ``"energy"``.
        n: Number of top rows to return.
        start: First local day of the filter window (inclusive). Defaults to
            the epoch when ``None``.
        end: Last local day of the filter window (inclusive). Defaults to a
            far-future date when ``None``.
        title: Override the auto-generated chart title.
        tz: IANA timezone for start/end conversion and label formatting.

    Returns:
        A :class:`RankedListData` with up to ``n`` ranked rows.
    """
    if start is None or end is None:
        utc_start = datetime(1970, 1, 1)
        utc_end = datetime(2100, 1, 1)
    else:
        utc_start, utc_end = _utc_bounds(start, end, tz)

    rows = conn.execute(_SQL_TOP_WORKOUTS, [activity_type, utc_start, utc_end]).fetchall()

    # Sort in Python; None values sort last
    def _sort_key(r: tuple) -> float:  # type: ignore[type-arg]
        _, _act, _start_utc, duration, _dur_unit, avg_hr, _max_hr, distance_m, energy_kj = r
        val: float | None
        if metric == "distance":
            val = distance_m
        elif metric == "duration":
            val = duration
        elif metric == "avg_hr":
            val = avg_hr
        else:  # energy
            val = energy_kj
        return val if val is not None else float("-inf")

    rows_sorted = sorted(rows, key=_sort_key, reverse=True)[:n]

    ranked_rows: list[RankedListRow] = []
    for row in rows_sorted:
        (
            _,
            act_type,
            start_date_utc,
            duration,
            duration_unit,
            avg_hr,
            _max_hr,
            distance_m,
            energy_kj,
        ) = row

        local_dt = _to_local_dt(start_date_utc, tz)
        local_date_str = local_dt.strftime("%Y-%m-%d")
        label = f"{act_type} — {local_date_str}"

        duration_min = minutes_from_duration(duration, duration_unit)

        distance_km = distance_m / 1000.0 if distance_m is not None else None

        if metric == "distance":
            primary_val: float | None = distance_km
            primary_unit = "km"
            secondary_val: float | None = duration_min
            secondary_unit: str | None = "min"
        elif metric == "duration":
            primary_val = duration_min
            primary_unit = "min"
            secondary_val = distance_km
            secondary_unit = "km"
        elif metric == "avg_hr":
            primary_val = avg_hr
            primary_unit = "bpm"
            secondary_val = duration_min
            secondary_unit = "min"
        else:  # energy
            primary_val = energy_kj
            primary_unit = "kJ"
            secondary_val = duration_min
            secondary_unit = "min"

        if primary_val is None:
            continue

        ranked_rows.append(
            RankedListRow(
                rank=len(ranked_rows) + 1,
                label=label,
                value=primary_val,
                unit=primary_unit,
                secondary_value=secondary_val,
                secondary_unit=secondary_unit,
            )
        )

    auto_title = title or f"Top {n} {activity_type} by {metric.replace('_', ' ').title()}"
    return RankedListData(title=auto_title, rows=ranked_rows)


def get_trend(
    conn: duckdb.DuckDBPyConnection,
    metric_id: str,
    granularity: Literal["day", "week", "month"],
    start: date,
    end: date,
    aggregation: Literal["avg", "sum"] | None = None,
    tz: str = DEFAULT_TZ,
) -> TrendChartData:
    """Fetch a time-bucketed trend series for a health metric.

    Args:
        conn: Open DuckDB connection.
        metric_id: Apple Health metric identifier (e.g.
            ``"HKQuantityTypeIdentifierRestingHeartRate"``).
        granularity: Bucket size: ``"day"``, ``"week"``, or ``"month"``.
        start: First local day of the trend window (inclusive).
        end: Last local day of the trend window (inclusive).
        aggregation: How to aggregate values within a bucket. Defaults to the
            value from :data:`~app.db.aggregations.METRIC_AGGREGATION`, or
            ``"avg"`` for unknown metrics.
        tz: IANA timezone for UTC conversion and local-day bucketing.

    Returns:
        A :class:`TrendChartData` with one :class:`TrendPoint` per bucket.
    """
    agg = aggregation or METRIC_AGGREGATION.get(metric_id, "avg")
    utc_start, utc_end = _utc_bounds(start, end, tz)

    rows = conn.execute(_SQL_TREND, [metric_id, utc_start, utc_end]).fetchall()

    # Group by bucket in Python
    bucket_values: dict[str, list[float]] = {}
    for start_date_utc, value in rows:
        local_dt = _to_local_dt(start_date_utc, tz)
        key = bucket_key(local_dt.date(), granularity)
        bucket_values.setdefault(key, []).append(float(value))

    # Aggregate
    aggregated: dict[str, float] = {}
    for key, vals in bucket_values.items():
        if agg == "sum":
            aggregated[key] = sum(vals)
        else:
            aggregated[key] = sum(vals) / len(vals)

    # Fill all buckets, None for missing
    all_buckets = generate_buckets(start, end, granularity)
    series = [TrendPoint(bucket=b, value=aggregated.get(b)) for b in all_buckets]

    label, unit = METRIC_META.get(metric_id, (metric_id, ""))
    chart_title = f"{label} Trend"

    return TrendChartData(
        title=chart_title,
        metric_label=label,
        metric_unit=unit,
        granularity=granularity,
        series=series,
    )


def get_period_summary(
    conn: duckdb.DuckDBPyConnection,
    period_start: date,
    period_end: date,
    title: str | None = None,
    tz: str = DEFAULT_TZ,
) -> PeriodSummaryData:
    """Build a summary of training metrics for a date range.

    Args:
        conn: Open DuckDB connection.
        period_start: First local day of the period (inclusive).
        period_end: Last local day of the period (inclusive).
        title: Override the auto-generated summary title.
        tz: IANA timezone for UTC bounds conversion.

    Returns:
        A :class:`PeriodSummaryData` with four metrics: sessions, distance,
        duration, and active energy.
    """
    utc_start, utc_end = _utc_bounds(period_start, period_end, tz)

    stats_row = conn.execute(_SQL_WORKOUTS_STATS, [utc_start, utc_end]).fetchone()
    session_count: float | None = stats_row[0] if stats_row else None
    total_duration_raw: float | None = stats_row[1] if stats_row else None

    dist_row = conn.execute(_SQL_DISTANCE, [utc_start, utc_end]).fetchone()
    total_distance_m: float | None = dist_row[0] if dist_row else None

    energy_row = conn.execute(_SQL_ENERGY, [utc_start, utc_end]).fetchone()
    total_energy_kj: float | None = energy_row[0] if energy_row else None

    # When no workouts, set derived metrics to None
    no_workouts = session_count is None or session_count == 0
    total_duration_min = None if no_workouts or total_duration_raw is None else total_duration_raw
    total_distance_km = (
        None if no_workouts or total_distance_m is None else total_distance_m / 1000.0
    )
    energy_val = None if no_workouts else total_energy_kj

    auto_title = (
        title or f"Training Summary: {period_start.isoformat()} to {period_end.isoformat()}"
    )

    metrics: list[PeriodMetric] = [
        PeriodMetric(label="Workouts", value=session_count, unit="sessions"),
        PeriodMetric(label="Total Distance", value=total_distance_km, unit="km"),
        PeriodMetric(label="Total Duration", value=total_duration_min, unit="min"),
        PeriodMetric(label="Active Energy", value=energy_val, unit="kJ"),
    ]

    return PeriodSummaryData(
        title=auto_title,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
    )


def _period_stats(
    conn: duckdb.DuckDBPyConnection,
    utc_start: datetime,
    utc_end: datetime,
    activity_type: str | None,
) -> dict[str, float | None]:
    """Fetch aggregate training stats for a UTC-bounded period.

    Args:
        conn: Open DuckDB connection.
        utc_start: Start of window (UTC naive, inclusive).
        utc_end: End of window (UTC naive, exclusive).
        activity_type: Filter to a specific activity type when set; otherwise
            aggregates across all activities.

    Returns:
        Dict with keys ``"sessions"``, ``"duration_min"``, ``"distance_m"``,
        ``"energy_kj"`` — each value is ``float | None``.
    """
    if activity_type:
        stats_row = conn.execute(
            _SQL_WORKOUTS_STATS_FILTERED, [utc_start, utc_end, activity_type]
        ).fetchone()
        dist_row = conn.execute(
            _SQL_DISTANCE_FILTERED, [utc_start, utc_end, activity_type]
        ).fetchone()
        energy_row = conn.execute(
            _SQL_ENERGY_FILTERED, [utc_start, utc_end, activity_type]
        ).fetchone()
    else:
        stats_row = conn.execute(_SQL_WORKOUTS_STATS, [utc_start, utc_end]).fetchone()
        dist_row = conn.execute(_SQL_DISTANCE, [utc_start, utc_end]).fetchone()
        energy_row = conn.execute(_SQL_ENERGY, [utc_start, utc_end]).fetchone()

    sessions: float | None = stats_row[0] if stats_row else None
    duration_min: float | None = stats_row[1] if stats_row else None
    distance_m: float | None = dist_row[0] if dist_row else None
    energy_kj: float | None = energy_row[0] if energy_row else None

    return {
        "sessions": sessions,
        "duration_min": duration_min,
        "distance_m": distance_m,
        "energy_kj": energy_kj,
    }


def get_comparison(
    conn: duckdb.DuckDBPyConnection,
    this_start: date,
    this_end: date,
    last_start: date,
    last_end: date,
    this_label: str,
    last_label: str,
    activity_type: str | None = None,
    title: str | None = None,
    tz: str = DEFAULT_TZ,
) -> ComparisonData:
    """Compare training metrics between two consecutive periods.

    Args:
        conn: Open DuckDB connection.
        this_start: First local day of the current period (inclusive).
        this_end: Last local day of the current period (inclusive).
        last_start: First local day of the prior period (inclusive).
        last_end: Last local day of the prior period (inclusive).
        this_label: Human-readable label for the current period.
        last_label: Human-readable label for the prior period.
        activity_type: When set, restricts comparison to this activity type.
        title: Override the auto-generated comparison title.
        tz: IANA timezone for UTC bounds conversion.

    Returns:
        A :class:`ComparisonData` with four :class:`ComparisonMetric` rows.
    """
    this_utc_start, this_utc_end = _utc_bounds(this_start, this_end, tz)
    last_utc_start, last_utc_end = _utc_bounds(last_start, last_end, tz)

    this_stats = _period_stats(conn, this_utc_start, this_utc_end, activity_type)
    last_stats = _period_stats(conn, last_utc_start, last_utc_end, activity_type)

    # Convert distance from m to km
    this_dist_km = (
        this_stats["distance_m"] / 1000.0 if this_stats["distance_m"] is not None else None
    )
    last_dist_km = (
        last_stats["distance_m"] / 1000.0 if last_stats["distance_m"] is not None else None
    )

    metrics: list[ComparisonMetric] = [
        ComparisonMetric(
            label="Sessions",
            this_value=this_stats["sessions"],
            last_value=last_stats["sessions"],
            delta=compute_delta(this_stats["sessions"], last_stats["sessions"]),
            unit="sessions",
            direction=compute_direction(this_stats["sessions"], last_stats["sessions"]),
        ),
        ComparisonMetric(
            label="Total Distance",
            this_value=this_dist_km,
            last_value=last_dist_km,
            delta=compute_delta(this_dist_km, last_dist_km),
            unit="km",
            direction=compute_direction(this_dist_km, last_dist_km),
        ),
        ComparisonMetric(
            label="Total Duration",
            this_value=this_stats["duration_min"],
            last_value=last_stats["duration_min"],
            delta=compute_delta(this_stats["duration_min"], last_stats["duration_min"]),
            unit="min",
            direction=compute_direction(this_stats["duration_min"], last_stats["duration_min"]),
        ),
        ComparisonMetric(
            label="Active Energy",
            this_value=this_stats["energy_kj"],
            last_value=last_stats["energy_kj"],
            delta=compute_delta(this_stats["energy_kj"], last_stats["energy_kj"]),
            unit="kJ",
            direction=compute_direction(this_stats["energy_kj"], last_stats["energy_kj"]),
        ),
    ]

    activity_label = "All Activities" if not activity_type else activity_type
    auto_title = title or f"{activity_label}: {this_label} vs {last_label}"

    return ComparisonData(
        title=auto_title,
        this_period_label=this_label,
        last_period_label=last_label,
        metrics=metrics,
    )


def get_fallback(
    question: str,
    text: str | None = None,
    table: list[FallbackTableRow] | None = None,
) -> FallbackData:
    """Build a fallback payload for questions the query layer cannot answer.

    Args:
        question: The original user question.
        text: Optional free-text answer.
        table: Optional key-value table of structured data.

    Returns:
        A :class:`FallbackData` payload.
    """
    return FallbackData(question=question, table=table, text=text)
