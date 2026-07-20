"""Versioned, allowlisted projections for optional provider messages.

These functions deliberately accept untrusted dictionaries but only emit the
small set of facts a planner or narrator needs.  They are the egress boundary:
callers must not interpolate tool payloads directly into provider messages.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

PLANNING_PROJECTION_VERSION = "v1"
NARRATION_PROJECTION_VERSION = "v1"

_ALLOWED_FACT_KEYS = frozenset(
    {
        "activity_type",
        "avg_heart_rate",
        "calories",
        "count",
        "date",
        "distance_meters",
        "distance_unit",
        "duration_minutes",
        "end_date",
        "energy_burned_kj",
        "elevation_ascent_meters",
        "label",
        "max_heart_rate",
        "metric",
        "period",
        "start_date",
        "total_distance_meters",
        "total_duration_minutes",
        "unit",
        "value",
        "workouts",
    }
)


def _compact_value(value: object) -> str | int | float | list[object] | dict[str, object] | None:
    if isinstance(value, str | bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [item for item in (_compact_value(item) for item in value) if item is not None]
    if isinstance(value, dict):
        return {
            key: compacted
            for key, item in value.items()
            if key in _ALLOWED_FACT_KEYS
            if (compacted := _compact_value(item)) is not None
        }
    return None


def planning_projection(question: str, data_context: str) -> dict[str, str]:
    """Return the only user and dataset fields allowed to remote planning."""
    return {
        "projection_version": PLANNING_PROJECTION_VERSION,
        "question": question,
        "dataset_context": data_context,
    }


def narration_projection(
    question: str, tool_name: str, payload: dict[str, Any]
) -> dict[str, object]:
    """Return compact template facts, excluding all unrecognised payload keys."""
    facts = _compact_value(payload)
    return {
        "projection_version": NARRATION_PROJECTION_VERSION,
        "question": question,
        "tool_name": tool_name,
        "facts": facts if isinstance(facts, dict) else {},
    }
