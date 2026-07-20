"""Typed registry for local analytics exposed by chat and dashboard adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from app.analytics.metric_catalog import METRIC_CATALOG
from app.models.templates import PeriodSummaryData, TrendChartData

_SQL_ACTIVITY_SUMMARY = """
SELECT date_components, active_energy_burned, active_energy_burned_goal,
       apple_exercise_time, apple_exercise_time_goal,
       apple_stand_hours, apple_stand_hours_goal
FROM activity_summaries
WHERE date_components >= ? AND date_components <= ?
ORDER BY date_components DESC
"""

type ActivitySummaryRow = tuple[
    str,
    float | None,
    float | None,
    float | None,
    float | None,
    int | None,
    int | None,
]

type WorkoutCollectionRow = tuple[
    int,
    str,
    datetime,
    float | None,
    str | None,
    str,
    float | None,
    float | None,
    float | None,
]


class WorkoutCollectionInput(BaseModel):
    """Validated input for the paged local workout collection."""

    start: date | None = None
    end: date | None = None
    activity_type: str | None = Field(default=None, min_length=1, max_length=160)
    source: str | None = Field(default=None, min_length=1, max_length=160)
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class WorkoutDetailInput(BaseModel):
    """Validated dataset-local workout detail reference."""

    workout_id: int = Field(ge=1)
    fingerprint: str | None = Field(default=None, pattern="^[a-f0-9]{16}$")


class PeriodSummaryInput(BaseModel):
    """Validated training-summary period and display title."""

    start: date
    end: date
    title: str | None = Field(default=None, max_length=160)


class MetricTrendInput(BaseModel):
    """Validated catalog metric trend request."""

    metric_id: str
    start: date
    end: date
    granularity: Literal["day", "week", "month"]
    aggregation: Literal["sum", "avg"] | None = None


class ActivitySummaryInput(BaseModel):
    """Validated local activity-ring period."""

    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class QueryDefinition:
    """Public contract and safety declarations for one local analytical query."""

    name: str
    version: str
    timezone: str
    unit: str
    dependencies: tuple[str, ...]
    empty_state: str
    success_state: str
    error_state: str
    input_fields: tuple[str, ...]
    metric_ids: tuple[str, ...]
    source_policy: str
    overlap_policy: str
    privacy_projection: Literal["none", "compact_facts"]
    input_model: type[BaseModel]


QUERY_REGISTRY: dict[str, QueryDefinition] = {
    "workout_collection": QueryDefinition(
        "workout_collection",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics"),
        "empty_list",
        "success",
        "unavailable",
        ("start", "end", "activity_type", "source", "cursor", "limit"),
        ("workouts",),
        "Workout rows remain distinct local activity events.",
        "No record-interval aggregation applies to workout rows.",
        "none",
        WorkoutCollectionInput,
    ),
    "workout_detail": QueryDefinition(
        "workout_detail",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics", "workout_routes"),
        "not_found",
        "success",
        "not_found",
        ("workout_id", "fingerprint"),
        ("workouts",),
        "Workout detail is sourced only from the dataset-local workout and route tables.",
        "Route points preserve their recorded order after local validation.",
        "none",
        WorkoutDetailInput,
    ),
    "period_summary": QueryDefinition(
        "period_summary",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics"),
        "zero_summary",
        "success",
        "unavailable",
        ("start", "end", "title"),
        ("workouts",),
        "Workout statistics are normalized from the selected local workout rows.",
        "Each workout contributes once to a period summary.",
        "compact_facts",
        PeriodSummaryInput,
    ),
    "metric_trend": QueryDefinition(
        "metric_trend",
        "v1",
        "Asia/Singapore",
        "metric_specific",
        ("records",),
        "missing_buckets",
        "success",
        "unsupported_metric",
        ("metric_id", "start", "end", "granularity"),
        ("steps", "active_energy", "resting_hr", "hrv"),
        "Metric-specific source values are projected from local records only.",
        "Catalog aggregation defines sum versus average per metric.",
        "compact_facts",
        MetricTrendInput,
    ),
    "activity_summary": QueryDefinition(
        "activity_summary",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("activity_summaries",),
        "empty_list",
        "success",
        "unavailable",
        ("start", "end"),
        ("activity_rings",),
        "Daily activity summaries remain local and source-aware.",
        "One declared activity summary is used per local day.",
        "none",
        ActivitySummaryInput,
    ),
}


def get_query_definition(name: str) -> QueryDefinition:
    """Return a declared registry entry or reject unsupported analytical names."""
    try:
        return QUERY_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported analytics query: {name}") from exc


def validate_query_catalogue() -> None:
    """Reject incomplete query declarations before adapters expose them."""
    for name, definition in QUERY_REGISTRY.items():
        if not definition.input_fields:
            raise ValueError(f"Query {name} must declare input fields")
        if not definition.success_state or not definition.empty_state or not definition.error_state:
            raise ValueError(f"Query {name} must declare success, empty, and error states")
        if not definition.source_policy or not definition.overlap_policy:
            raise ValueError(f"Query {name} must declare source and overlap policy")
        unknown_metrics = set(definition.metric_ids).difference(METRIC_CATALOG)
        if unknown_metrics:
            raise ValueError(f"Query {name} declares unknown metrics: {sorted(unknown_metrics)}")


def execute_metric_trend(conn: object, values: dict[str, object]) -> TrendChartData:
    """Validate and execute the registry-owned local metric trend query."""
    from app.db import queries

    args = MetricTrendInput.model_validate(values)
    return queries.get_trend(
        conn,  # type: ignore[arg-type]
        args.metric_id,
        args.granularity,
        args.start,
        args.end,
        aggregation=args.aggregation,
    )


def execute_period_summary(conn: object, values: dict[str, object]) -> PeriodSummaryData:
    """Validate and execute the registry-owned training period summary."""
    from app.db import queries

    args = PeriodSummaryInput.model_validate(values)
    return queries.get_period_summary(conn, args.start, args.end, title=args.title)  # type: ignore[arg-type]


def execute_activity_summary(conn: object, values: dict[str, object]) -> list[ActivitySummaryRow]:
    """Validate and execute the registry-owned activity-ring fact query."""
    args = ActivitySummaryInput.model_validate(values)
    if args.start is None or args.end is None:
        raise ValueError("Activity summary execution requires an absolute start and end date")
    rows = conn.execute(  # type: ignore[union-attr]
        _SQL_ACTIVITY_SUMMARY, [args.start.isoformat(), args.end.isoformat()]
    ).fetchall()
    return cast(list[ActivitySummaryRow], rows)


def execute_workout_collection(
    conn: object, values: dict[str, object]
) -> list[WorkoutCollectionRow]:
    """Validate and execute the registry-owned cursor-paged workout collection."""
    from app.db import queries

    args = WorkoutCollectionInput.model_validate(values)
    if args.start is None or args.end is None:
        raise ValueError("Workout collection execution requires an absolute start and end date")
    cursor_date: datetime | None = None
    cursor_id: int | None = None
    if args.cursor is not None:
        try:
            date_text, id_text = args.cursor.rsplit("|", maxsplit=1)
            cursor_date = datetime.fromisoformat(date_text)
            cursor_id = int(id_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid workout cursor") from exc
    rows = queries.get_workout_collection(
        conn,  # type: ignore[arg-type]
        args.start,
        args.end,
        args.activity_type,
        args.source,
        cursor_date,
        cursor_id,
        args.limit + 1,
    )
    return cast(list[WorkoutCollectionRow], rows)
