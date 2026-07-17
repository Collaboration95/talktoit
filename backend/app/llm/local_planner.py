"""Deterministic fallback plans for common health-data questions.

The remote model remains the primary planner.  This module keeps the command
line useful when that model is unavailable or produces malformed JSON, without
sending any additional health data off-device.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.db.data_profile import DataProfile


def _activity_type(question: str) -> str | None:
    lower = question.lower()
    if "run" in lower or "jog" in lower:
        return "Running"
    if "bike" in lower or "cycl" in lower:
        return "Cycling"
    if any(word in lower for word in ("gym", "weight", "strength")):
        return "TraditionalStrengthTraining"
    return None


def _month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start - timedelta(days=1)


def _period_for_question(question: str, as_of: date) -> tuple[date, date, str] | None:
    lower = question.lower()
    if "last month" in lower:
        current_start, _current_end = _month_bounds(as_of)
        previous_day = current_start - timedelta(days=1)
        start, end = _month_bounds(previous_day)
        return start, end, start.strftime("%B %Y")
    if "this month" in lower:
        start, _end = _month_bounds(as_of)
        return start, as_of, start.strftime("%B %Y")
    if "last week" in lower:
        current_week_start = as_of - timedelta(days=as_of.weekday())
        end = current_week_start - timedelta(days=1)
        start = end - timedelta(days=6)
        return start, end, f"{start:%b %-d}-{end:%b %-d}"
    if "this year" in lower or "year" in lower:
        return date(as_of.year, 1, 1), as_of, str(as_of.year)
    return None


def _comparison_plan(question: str, as_of: date, activity_type: str | None) -> dict[str, Any]:
    this_start, this_end = _month_bounds(as_of)
    this_end = min(this_end, as_of)
    last_start, last_end = _month_bounds(this_start - timedelta(days=1))
    arguments: dict[str, Any] = {
        "this_start": this_start.isoformat(),
        "this_end": this_end.isoformat(),
        "last_start": last_start.isoformat(),
        "last_end": last_end.isoformat(),
        "this_label": this_start.strftime("%B %Y"),
        "last_label": last_start.strftime("%B %Y"),
    }
    if activity_type is not None:
        arguments["activity_type"] = activity_type
    return {"tool_name": "get_comparison", "arguments": arguments}


def plan_local_question(question: str, profile: DataProfile) -> dict[str, Any] | None:
    """Return a safe local tool plan for well-known question patterns.

    Returns ``None`` when the wording is outside the deliberately small
    fallback vocabulary so the caller can show the normal fallback response.
    """
    if profile.latest_date is None:
        return None

    lower = question.lower()
    as_of = profile.latest_date
    activity_type = _activity_type(question)
    period = _period_for_question(question, as_of)

    if "compare" in lower and ("month" in lower or "week" in lower):
        return _comparison_plan(question, as_of, activity_type)

    if "resting heart" in lower or "resting hr" in lower:
        start, end, _label = period or (as_of - timedelta(days=89), as_of, "Latest 90 days")
        return {
            "tool_name": "get_trend",
            "arguments": {
                "metric_id": "HKQuantityTypeIdentifierRestingHeartRate",
                "granularity": "week",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        }

    if "training volume" in lower or "training summary" in lower:
        start, end, _label = period or (as_of - timedelta(days=6), as_of, "Latest 7 days")
        return {
            "tool_name": "get_period_summary",
            "arguments": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        }

    if activity_type is not None and any(
        phrase in lower for phrase in ("top", "longest", "highest heart", "highest hr")
    ):
        metric = "avg_hr" if "heart" in lower or " hr" in lower else "duration"
        arguments: dict[str, Any] = {"activity_type": activity_type, "metric": metric, "n": 5}
        if "which" in lower:
            arguments["n"] = 1
        if period is not None:
            start, end, _label = period
            arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return {"tool_name": "get_top_workouts", "arguments": arguments}

    if activity_type is not None and any(
        phrase in lower for phrase in ("last", "latest", "most recent")
    ):
        return {"tool_name": "get_last_workout", "arguments": {"activity_type": activity_type}}

    return None
