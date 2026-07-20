"""Typed registry for local analytics exposed by chat and dashboard adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QueryDefinition:
    """Public contract and safety declarations for one local analytical query."""

    name: str
    version: str
    timezone: str
    unit: str
    dependencies: tuple[str, ...]
    empty_state: str
    privacy_projection: Literal["none", "compact_facts"]


QUERY_REGISTRY: dict[str, QueryDefinition] = {
    "workout_collection": QueryDefinition(
        "workout_collection",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics"),
        "empty_list",
        "none",
    ),
    "workout_detail": QueryDefinition(
        "workout_detail",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics", "workout_routes"),
        "not_found",
        "none",
    ),
    "period_summary": QueryDefinition(
        "period_summary",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("workouts", "workout_statistics"),
        "zero_summary",
        "compact_facts",
    ),
    "metric_trend": QueryDefinition(
        "metric_trend",
        "v1",
        "Asia/Singapore",
        "metric_specific",
        ("records",),
        "missing_buckets",
        "compact_facts",
    ),
    "activity_summary": QueryDefinition(
        "activity_summary",
        "v1",
        "Asia/Singapore",
        "mixed",
        ("activity_summaries",),
        "empty_list",
        "none",
    ),
}


def get_query_definition(name: str) -> QueryDefinition:
    """Return a declared registry entry or reject unsupported analytical names."""
    try:
        return QUERY_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported analytics query: {name}") from exc
