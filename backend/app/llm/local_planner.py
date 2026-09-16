"""Deterministic fallback plans for common health-data questions.

The remote model remains the primary planner.  This module keeps the command
line useful when that model is unavailable or produces malformed JSON, without
sending any additional health data off-device.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.db.data_profile import DataProfile
from app.llm.vocabulary import activity_type_from_question, contains_word


def _activity_type(question: str) -> str | None:
    return activity_type_from_question(question)


def _month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return start, next_start - timedelta(days=1)


def _period_for_question(question: str, as_of: date) -> tuple[date, date, str] | None:
    lower = question.lower()
    month_match = re.search(
        r"\b(?:in|for|during)?\s*"
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(\d{4})\b",
        lower,
    )
    if month_match:
        month = datetime.strptime(f"{month_match.group(1)} {month_match.group(2)}", "%B %Y").date()
        start, end = _month_bounds(month)
        return start, end, start.strftime("%B %Y")
    if re.search(r"\blast month\b", lower):
        current_start, _current_end = _month_bounds(as_of)
        previous_day = current_start - timedelta(days=1)
        start, end = _month_bounds(previous_day)
        return start, end, start.strftime("%B %Y")
    if re.search(r"\bthis month\b", lower):
        start, _end = _month_bounds(as_of)
        return start, as_of, start.strftime("%B %Y")
    if re.search(r"\blast week\b", lower):
        current_week_start = as_of - timedelta(days=as_of.weekday())
        end = current_week_start - timedelta(days=1)
        start = end - timedelta(days=6)
        return start, end, f"{start:%b %-d}-{end:%b %-d}"
    if re.search(r"\blast year\b", lower):
        start = date(as_of.year - 1, 1, 1)
        end = date(as_of.year - 1, 12, 31)
        return start, end, str(as_of.year - 1)
    if re.search(r"\b(?:this year|year to date)\b", lower):
        return date(as_of.year, 1, 1), as_of, str(as_of.year)
    if re.search(r"\bthis week\b", lower):
        start = as_of - timedelta(days=as_of.weekday())
        return start, as_of, f"{start:%b %-d}-{as_of:%b %-d}"
    return None


def _trend_metric(question: str) -> str | None:
    lower = question.casefold()
    if "resting heart" in lower or "resting hr" in lower:
        return "HKQuantityTypeIdentifierRestingHeartRate"
    if re.search(r"\bsteps?\b", lower):
        return "steps"
    if re.search(r"\bhrv\b", lower):
        return "hrv"
    if "active energy" in lower:
        return "active_energy"
    return None


def _requested_granularity(question: str) -> str:
    lower = question.casefold()
    if re.search(r"\b(?:daily|day|days)\b", lower):
        return "day"
    if re.search(r"\b(?:monthly|month|months)\b", lower):
        return "month"
    return "week"


def _fallback_plan(text: str) -> dict[str, Any]:
    return {"tool_name": "get_fallback_answer", "arguments": {"text": text}}


def _comparison_plan(
    question: str, as_of: date, activity_type: str | None, granularity: str
) -> dict[str, Any]:
    if granularity == "week":
        this_start = as_of - timedelta(days=as_of.weekday())
        this_end = min(this_start + timedelta(days=6), as_of)
        last_end = this_start - timedelta(days=1)
        last_start = last_end - timedelta(days=6)
        this_label = f"{this_start:%d %b} to {this_end:%d %b %Y}"
        last_label = f"{last_start:%d %b} to {last_end:%d %b %Y}"
    else:
        this_start, this_end = _month_bounds(as_of)
        this_end = min(this_end, as_of)
        last_start, last_end = _month_bounds(this_start - timedelta(days=1))
        this_label = this_start.strftime("%B %Y")
        last_label = last_start.strftime("%B %Y")
    arguments: dict[str, Any] = {
        "this_start": this_start.isoformat(),
        "this_end": this_end.isoformat(),
        "last_start": last_start.isoformat(),
        "last_end": last_end.isoformat(),
        "this_label": this_label,
        "last_label": last_label,
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

    trend_metric = _trend_metric(question)

    if contains_word(lower, "compare") and trend_metric is not None:
        return _fallback_plan(
            "Comparing health metrics between periods is not supported yet. "
            "I can show a trend for that metric instead."
        )

    if contains_word(lower, "compare") and (
        contains_word(lower, "month") or contains_word(lower, "week")
    ):
        granularity = "week" if contains_word(lower, "week") else "month"
        return _comparison_plan(question, as_of, activity_type, granularity)

    if trend_metric is not None:
        start, end, _label = period or (as_of - timedelta(days=89), as_of, "Latest 90 days")
        return {
            "tool_name": "get_trend",
            "arguments": {
                "metric_id": trend_metric,
                "granularity": _requested_granularity(question),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        }

    if (
        "training volume" in lower
        or "training summary" in lower
        or (
            activity_type is not None
            and ("volume" in lower or re.search(r"\bhow many\b", lower) is not None)
        )
        or (activity_type is None and re.search(r"\bhow many workouts?\b", lower) is not None)
    ):
        start, end, _label = period or (as_of - timedelta(days=6), as_of, "Latest 7 days")
        arguments: dict[str, Any] = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        if activity_type is not None:
            arguments["activity_type"] = activity_type
        return {
            "tool_name": "get_period_summary",
            "arguments": arguments,
        }

    if activity_type is not None and any(
        phrase in lower for phrase in ("top", "longest", "highest heart", "highest hr")
    ):
        if "pace" in lower:
            return _fallback_plan(
                "Ranking workouts by pace is not supported yet. "
                "I can rank them by distance, duration, heart rate, or energy."
            )
        if "distance" in lower:
            metric = "distance"
        elif "heart" in lower or " hr" in lower:
            metric = "avg_hr"
        elif "energy" in lower or "calorie" in lower:
            metric = "energy"
        else:
            metric = "duration"
        count_match = re.search(r"\btop\s+(\d{1,3})\b", lower)
        arguments: dict[str, Any] = {
            "activity_type": activity_type,
            "metric": metric,
            "n": int(count_match.group(1)) if count_match else 5,
        }
        if "which" in lower:
            arguments["n"] = 1
        if period is not None:
            start, end, _label = period
            arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return {"tool_name": "get_top_workouts", "arguments": arguments}

    # Keep the broad “most recent workout” wording for the model planner: it
    # may carry conversational context that tells it how to scope the request.
    # The explicit “last workout” command is safely unscoped.
    asks_for_latest_workout = re.search(r"\blast workout\b", lower)
    if (activity_type is not None or asks_for_latest_workout) and any(
        phrase in lower for phrase in ("last", "latest", "most recent")
    ):
        arguments = {"activity_type": activity_type} if activity_type is not None else {}
        if "long" in lower:
            arguments["min_duration_minutes"] = 30
        if period is not None:
            start, end, _label = period
            arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return {"tool_name": "get_last_workout", "arguments": arguments}

    return None
