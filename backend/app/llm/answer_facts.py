"""Safe, template-specific facts for optional answer narration.

This module is the health-data egress boundary for narration.  Query payloads
are deliberately *not* recursively compacted: each supported template gets a
small, documented projection and every other key is discarded.  The result is
also suitable for the deterministic narration used when the optional provider
is unavailable.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

NARRATION_FACTS_VERSION = "v2"

TemplateId = Literal[
    "workout_card", "ranked_list", "trend_chart", "period_summary", "comparison", "fallback"
]

_MAX_RANKED_ROWS = 10
_MAX_METRICS = 8
_MAX_TREND_POINTS = 8


def _text(value: object) -> str | None:
    """Return a bounded string only when it is already a string."""
    if not isinstance(value, str):
        return None
    return value[:200]


def _number(value: object, unit: str = "") -> int | float | None:
    """Round finite measurements as the UI does without changing their unit."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(float(value)):
        return None
    places = 1 if unit == "km" else 0
    quantum = Decimal("0.1") if places else Decimal("1")
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(rounded) if places else int(rounded)


def _date_text(value: object) -> str | None:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return _text(value)


def _measurement(value: object, unit: object) -> dict[str, object] | None:
    unit_text = _text(unit)
    if unit_text is None:
        return None
    return {"value": _number(value, unit_text), "unit": unit_text}


def _workout_facts(payload: dict[str, Any]) -> dict[str, object]:
    facts: dict[str, object] = {}
    for key in ("activity_type",):
        if (value := _text(payload.get(key))) is not None:
            facts[key] = value
    if (value := _date_text(payload.get("date"))) is not None:
        facts["date"] = value

    duration = _measurement(payload.get("duration_minutes"), "min")
    if "duration_minutes" in payload and duration is not None:
        facts["duration"] = duration
    # ``distance_meters`` is deliberately named for its stored unit. Convert it
    # to the UI's compact km display, rather than pairing a meter value with a
    # payload-provided display label.
    raw_distance = payload.get("distance_meters")
    distance = (
        _measurement(float(raw_distance) / 1000, "km")
        if isinstance(raw_distance, int | float) and not isinstance(raw_distance, bool)
        else None
    )
    if "distance_meters" in payload and distance is not None:
        facts["distance"] = distance
    for source, target in (
        ("avg_heart_rate", "average_heart_rate"),
        ("max_heart_rate", "max_heart_rate"),
        ("energy_burned_kj", "energy"),
        ("elevation_ascent_meters", "elevation_ascent"),
    ):
        unit = "bpm" if "heart_rate" in source else "kJ" if source == "energy_burned_kj" else "m"
        measurement = _measurement(payload.get(source), unit)
        if source in payload and measurement is not None:
            facts[target] = measurement
    return facts


def _ranked_list_facts(payload: dict[str, Any]) -> dict[str, object]:
    facts: dict[str, object] = {}
    if (title := _text(payload.get("title"))) is not None:
        facts["title"] = title
    rows: list[dict[str, object]] = []
    raw_rows = payload.get("rows")
    if isinstance(raw_rows, list):
        for raw_row in raw_rows[:_MAX_RANKED_ROWS]:
            if not isinstance(raw_row, dict):
                continue
            unit = _text(raw_row.get("unit"))
            label = _text(raw_row.get("label"))
            rank = _number(raw_row.get("rank"))
            if unit is None or label is None or rank is None:
                continue
            row: dict[str, object] = {
                "rank": rank,
                "label": label,
                "value": _number(raw_row.get("value"), unit),
                "unit": unit,
            }
            secondary_unit = _text(raw_row.get("secondary_unit"))
            if secondary_unit is not None:
                row["secondary_value"] = _number(raw_row.get("secondary_value"), secondary_unit)
                row["secondary_unit"] = secondary_unit
            rows.append(row)
    facts["rows"] = rows
    return facts


def _representative_points(series: list[dict[str, object]]) -> list[dict[str, object]]:
    if len(series) <= _MAX_TREND_POINTS:
        return series
    half = _MAX_TREND_POINTS // 2
    return [*series[:half], *series[-half:]]


def _trend_facts(payload: dict[str, Any]) -> dict[str, object]:
    facts: dict[str, object] = {}
    for key in ("title", "metric_label", "metric_unit", "granularity"):
        if (value := _text(payload.get(key))) is not None:
            facts[key] = value
    unit = facts.get("metric_unit")
    raw_series = payload.get("series")
    series: list[dict[str, object]] = []
    if isinstance(raw_series, list) and isinstance(unit, str):
        for raw_point in raw_series:
            if not isinstance(raw_point, dict):
                continue
            bucket = _text(raw_point.get("bucket"))
            if bucket is None:
                continue
            # Missing values are an intentional fact, rather than a reason to
            # erase a bucket from the narration context.
            series.append({"bucket": bucket, "value": _number(raw_point.get("value"), unit)})
    facts["bucket_count"] = len(series)
    facts["missing_bucket_count"] = sum(point["value"] is None for point in series)
    facts["representative_points"] = _representative_points(series)
    return facts


def _period_summary_facts(payload: dict[str, Any]) -> dict[str, object]:
    facts: dict[str, object] = {}
    for key in ("title",):
        if (value := _text(payload.get(key))) is not None:
            facts[key] = value
    for source, target in (("period_start", "period_start"), ("period_end", "period_end")):
        if (value := _date_text(payload.get(source))) is not None:
            facts[target] = value
    facts["metrics"] = _metric_facts(payload.get("metrics"))
    return facts


def _metric_facts(raw_metrics: object) -> list[dict[str, object]]:
    metrics: list[dict[str, object]] = []
    if not isinstance(raw_metrics, list):
        return metrics
    for raw_metric in raw_metrics[:_MAX_METRICS]:
        if not isinstance(raw_metric, dict):
            continue
        label = _text(raw_metric.get("label"))
        unit = _text(raw_metric.get("unit"))
        if label is None or unit is None:
            continue
        metrics.append(
            {"label": label, "value": _number(raw_metric.get("value"), unit), "unit": unit}
        )
    return metrics


def _comparison_facts(payload: dict[str, Any]) -> dict[str, object]:
    facts: dict[str, object] = {}
    for key in ("title", "this_period_label", "last_period_label"):
        if (value := _text(payload.get(key))) is not None:
            facts[key] = value
    metrics: list[dict[str, object]] = []
    raw_metrics = payload.get("metrics")
    if isinstance(raw_metrics, list):
        for raw_metric in raw_metrics[:_MAX_METRICS]:
            if not isinstance(raw_metric, dict):
                continue
            label = _text(raw_metric.get("label"))
            unit = _text(raw_metric.get("unit"))
            direction = _text(raw_metric.get("direction"))
            if label is None or unit is None or direction not in {"up", "down", "flat"}:
                continue
            metrics.append(
                {
                    "label": label,
                    "this_value": _number(raw_metric.get("this_value"), unit),
                    "last_value": _number(raw_metric.get("last_value"), unit),
                    "delta": _number(raw_metric.get("delta"), unit),
                    "unit": unit,
                    "direction": direction,
                }
            )
    facts["metrics"] = metrics
    return facts


def narration_facts(template_id: str, payload: dict[str, Any]) -> dict[str, object]:
    """Project validated template data to compact, narration-safe facts.

    ``fallback`` intentionally has no facts. It is a terminal local response,
    so its text must never become an ungrounded prompt to an optional provider.
    Unknown template IDs likewise fail closed.
    """
    projectors = {
        "workout_card": _workout_facts,
        "ranked_list": _ranked_list_facts,
        "trend_chart": _trend_facts,
        "period_summary": _period_summary_facts,
        "comparison": _comparison_facts,
    }
    projector = projectors.get(template_id)
    return projector(payload) if projector is not None else {}


def deterministic_narrative(template_id: str, facts: dict[str, object]) -> str:
    """Return a modest grounded sentence when optional narration is unavailable."""
    if template_id == "workout_card":
        activity = facts.get("activity_type", "workout")
        date_value = facts.get("date")
        duration = facts.get("duration")
        distance = facts.get("distance")
        parts = [f"Your {activity} workout"]
        if isinstance(date_value, str):
            parts.append(f"was on {date_value}")
        if isinstance(duration, dict) and duration.get("value") is not None:
            parts.append(f"lasted {duration['value']} {duration['unit']}")
        if isinstance(distance, dict) and distance.get("value") is not None:
            parts.append(f"covered {distance['value']} {distance['unit']}")
        return " ".join(parts[:2]) + (", " + " and ".join(parts[2:]) if len(parts) > 2 else ".")
    if template_id == "ranked_list":
        rows = facts.get("rows")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            first = rows[0]
            return (
                f"The ranked list contains {len(rows)} results; #{first.get('rank')} "
                f"is {first.get('label')} at {first.get('value')} {first.get('unit')}."
            )
        return "No ranked results matched the requested scope."
    if template_id == "trend_chart":
        granularity = facts.get("granularity", "time-bucketed")
        metric_label = facts.get("metric_label", "metric")
        return (
            f"This {granularity} {metric_label} "
            f"trend has {facts.get('bucket_count', 0)} buckets, with "
            f"{facts.get('missing_bucket_count', 0)} missing values."
        )
    if template_id == "period_summary":
        metrics = facts.get("metrics")
        if isinstance(metrics, list) and metrics:
            text = ", ".join(
                f"{item.get('label')}: {item.get('value')} {item.get('unit')}"
                for item in metrics[:3]
                if isinstance(item, dict)
            )
            return f"{facts.get('title', 'Training summary')}: {text}."
    if template_id == "comparison":
        title = facts.get("title", "Comparison")
        current = facts.get("this_period_label", "the current period")
        previous = facts.get("last_period_label", "the prior period")
        return f"{title} compares {current} with {previous}."
    return "I found the matching data in your local health database."
