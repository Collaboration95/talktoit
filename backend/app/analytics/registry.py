"""Typed registry for local analytics exposed by chat and dashboard adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.analytics.metric_catalog import METRIC_CATALOG
from app.models.templates import TrendChartData


class WorkoutCollectionInput(BaseModel):
    """Validated input for the paged local workout collection."""

    start: date | None = None
    end: date | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=100)


class WorkoutDetailInput(BaseModel):
    """Validated dataset-local workout detail reference."""

    workout_id: int = Field(ge=1)
    fingerprint: str | None = Field(default=None, pattern="^[a-f0-9]{16}$")


class PeriodSummaryInput(BaseModel):
    """Validated training-summary period and optional activity scope."""

    start: date
    end: date
    activity_type: str | None = None


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
        ("start", "end", "cursor", "limit"),
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
        ("start", "end", "activity_type"),
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
