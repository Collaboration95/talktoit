"""Deterministic fallback plans for common health-data questions.

Recognized questions use deterministic plans before any optional provider.
Sleep wording always stays local, including requests outside the supported
grammar. Explicit metric comparisons never infer missing date periods.
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


def _fallback_plan(text: str, reason: str = "unsupported") -> dict[str, Any]:
    return {"tool_name": "get_fallback_answer", "arguments": {"text": text, "reason": reason}}


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


def is_sleep_question(question: str) -> bool:
    """Keep sleep wording local even when it is outside the supported grammar."""
    return (
        re.search(
            r"\b(?:sleep\w*|asleep|slept|insomnia|awake|awakenings?|bedtime|rem)\b|\bin[- ]?bed\b",
            question.casefold(),
        )
        is not None
    )


_MONTHS = (
    "january february march april may june july august september october november december".split()
)
_MONTH_PATTERN = "|".join(_MONTHS)


def _explicit_ranges(question: str) -> list[tuple[date, date]]:
    """Parse only complete ISO or bounded English date ranges; never infer a year."""
    text = question.casefold().replace("\u2013", "-").replace("—", "-")
    suffix = re.split(r"\b(?:from|between)\b", text, maxsplit=1)
    if len(suffix) != 2:
        return []
    date_text = suffix[1].strip().rstrip(".?!")
    iso_range = r"\d{4}-\d{2}-\d{2}\s+(?:to|through)\s+\d{4}-\d{2}-\d{2}"
    day_range = rf"\d{{1,2}}\s*-\s*\d{{1,2}}\s+(?:{_MONTH_PATTERN})\s+\d{{4}}"
    month_range = rf"(?:{_MONTH_PATTERN})\s+\d{{1,2}}\s*-\s*\d{{1,2}}(?:,?\s+\d{{4}})?"
    # Require the entire date clause, so an extra/incomplete date is never discarded.
    patterns = (iso_range, day_range, month_range)
    if not any(
        re.fullmatch(rf"{part}(?:\s+(?:with|vs\.?|versus|and)\s+{part})?", date_text)
        for part in patterns
    ):
        return []
    iso = re.findall(
        r"(?<![\d-])(\d{4}-\d{2}-\d{2})\s+(?:to|through)\s+"
        r"(\d{4}-\d{2}-\d{2})(?![\d-])",
        text,
    )
    if iso:
        # Reject extra singleton dates rather than silently ignoring an incomplete period.
        if len(re.findall(r"\d{4}-\d{2}-\d{2}", text)) != len(iso) * 2:
            return []
        try:
            periods = [(date.fromisoformat(start), date.fromisoformat(end)) for start, end in iso]
        except ValueError:
            return []
        return periods if all(start <= end for start, end in periods) else []
    day_first = re.findall(
        rf"\b(\d{{1,2}})\s*-\s*(\d{{1,2}})\s+({_MONTH_PATTERN})"
        r"\s+(\d{4})\b",
        text,
    )
    month_first = re.findall(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}})\s*-\s*(\d{{1,2}})"
        r"(?:,?\s+(\d{4}))?\b",
        text,
    )
    try:
        if day_first and not month_first:
            periods = [
                (
                    date(int(year), _MONTHS.index(month) + 1, int(start)),
                    date(int(year), _MONTHS.index(month) + 1, int(end)),
                )
                for start, end, month, year in day_first
            ]
        elif month_first and not day_first:
            years = [item[3] for item in month_first]
            # Only the documented trailing shared-year form supplies a missing year.
            shared_year = (
                years[-1]
                if len(years) == 2 and not years[0] and years[-1] and "between" in text
                else None
            )
            if any(not year for year in years) and shared_year is None:
                return []
            periods = [
                (
                    date(int(year or shared_year or "0"), _MONTHS.index(month) + 1, int(start)),
                    date(int(year or shared_year or "0"), _MONTHS.index(month) + 1, int(end)),
                )
                for month, start, end, year in month_first
            ]
        else:
            return []
    except ValueError:
        return []
    return periods if all(start <= end for start, end in periods) else []


def _metric_comparison_plan(question: str) -> dict[str, Any]:
    lower = question.casefold()
    metric_text = re.split(r"\b(?:from|between)\b", lower, maxsplit=1)[0]
    ids: list[str] = []
    for metric_id, pattern in (
        ("steps", r"\bsteps?\b"),
        ("resting_hr", r"\bresting (?:heart rate|hr)\b"),
        ("hrv", r"\bhrv(?: sdnn)?\b"),
    ):
        if re.search(pattern, metric_text):
            ids.append(metric_id)
            metric_text = re.sub(pattern, " ", metric_text)
    remaining = re.sub(r"\b(?:compare|my|and)\b|[,\s]", "", metric_text)
    ranges = _explicit_ranges(question)
    if remaining or not ids or len(ranges) != 2:
        return _fallback_plan(
            "Choose steps, resting HR, or HRV and give two complete date ranges, including years. "
            "For example: Compare steps from 2026-06-01 to 2026-06-07 vs "
            "2026-05-25 to 2026-05-31.",
            "clarification_needed",
        )
    (start, end), (prior_start, prior_end) = ranges
    from app.presentation import format_date_range

    return {
        "tool_name": "get_comparison",
        "arguments": {
            "this_start": start.isoformat(),
            "this_end": end.isoformat(),
            "last_start": prior_start.isoformat(),
            "last_end": prior_end.isoformat(),
            "this_label": format_date_range(start, end),
            "last_label": format_date_range(prior_start, prior_end),
            "metric_ids": ids,
        },
    }


def _sleep_date_range(text: str, as_of: date | None) -> tuple[date, date] | None:
    """Accept one complete supported date clause, never its first matching fragment."""
    scope = re.search(
        rf"\b(?:from|between|in|for|during|since|before|after|until|"
        rf"(?:this|last)\s+(?:week|month|year)|year to date|{_MONTH_PATTERN})\b|\b\d{{4}}-",
        text,
    )
    if scope is None:
        return None
    clause = text[scope.start() :].strip().rstrip(".?!")
    if re.match(r"(?:from|between)\b", clause):
        ranges = _explicit_ranges(clause)
        return ranges[0] if len(ranges) == 1 else None
    if as_of is None or not re.fullmatch(
        rf"(?:(?:in|for|during)\s+)?(?:"
        rf"(?:{_MONTH_PATTERN})\s+\d{{4}}|(?:this|last)\s+(?:week|month|year)|year to date)",
        clause,
    ):
        return None
    try:
        period = _period_for_question(clause, as_of)
    except ValueError:
        return None
    return (period[0], period[1]) if period is not None else None


def _sleep_plan(question: str, profile: DataProfile) -> dict[str, Any]:
    lower = question.casefold()
    # A coverage explanation may name included categories without asking to measure one.
    intent = re.sub(r"\bincluding awake and in[- ]?bed (?:records|intervals)\b", "", lower)
    if re.search(
        r"\b(?:stages?|rem|deep|core|light|asleep|awake|awakenings?|bedtime)\b|\bin[- ]?bed\b",
        intent,
    ):
        return _fallback_plan(
            "Sleep stages (REM, deep and core) and time asleep, awake or in bed are not supported "
            "in chat yet. I can show measured sleep interval coverage, including awake and "
            "in-bed records. Try: Show daily sleep last week."
        )
    if re.search(
        r"\b(?:why|improve|badly|quality|score|diagnos\w*|compare|insomnia|healthy|normal)\b", lower
    ):
        return _fallback_plan(
            "I can show measured sleep interval coverage, including awake and "
            "in-bed records. Ask for a sleep trend with a date range."
        )
    period = _sleep_date_range(intent, profile.latest_date)
    if period is None:
        return _fallback_plan(
            "Give a sleep trend date range, such as Show daily sleep last week "
            "or Show sleep from 2026-06-01 to 2026-06-07.",
            "clarification_needed",
        )
    start, end = period
    return {
        "tool_name": "get_sleep_trend",
        "arguments": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "granularity": _requested_granularity(question),
        },
    }


def plan_local_question(question: str, profile: DataProfile) -> dict[str, Any] | None:
    """Return a safe local tool plan for well-known question patterns.

    Returns ``None`` when the wording is outside the deliberately small
    fallback vocabulary so the caller can show the normal fallback response.
    """
    if is_sleep_question(question):
        return _sleep_plan(question, profile)
    if question.lower().strip().rstrip("?.!") in {
        "compare that",
        "compare this",
        "what about that",
        "show that",
    }:
        return _fallback_plan(
            "Select an answer with Ask about this answer, or name a workout type and date range.",
            "clarification_needed",
        )

    # Explicit metric dates do not require any data to exist.
    if re.search(r"\b(?:compare|versus|vs)\b", question.casefold()) and (
        _trend_metric(question) is not None
        or (
            _activity_type(question) is None
            and not re.search(r"\bworkouts?\b", question.casefold())
        )
    ):
        return _metric_comparison_plan(question)
    if profile.latest_date is None:
        return None

    lower = question.lower()
    as_of = profile.latest_date
    activity_type = _activity_type(question)
    period = _period_for_question(question, as_of)

    if "pace" in lower and any(word in lower for word in ("top", "rank", "fastest", "longest")):
        return _fallback_plan(
            "Ranking workouts by pace is not supported yet. Try: Top 5 longest runs this year."
        )

    trend_metric = _trend_metric(question)

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
        if "which" in lower and count_match is None:
            arguments["n"] = 1
        if period is not None:
            start, end, _label = period
            arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return {"tool_name": "get_top_workouts", "arguments": arguments}

    # A period word is a scope, not evidence that the user asked for a latest
    # workout.  Only explicit singular latest-workout wording reaches this
    # branch; plural period-only requests are left for an honest fallback.
    asks_for_latest_workout = re.search(
        r"\b(?:last|latest)\s+(?:long\s+)?(?:run|ride|workout|session)\b"
        r"|\bmost recent\s+(?:run|ride|session)\b",
        lower,
    )
    if asks_for_latest_workout:
        arguments = {"activity_type": activity_type} if activity_type is not None else {}
        if "long" in lower:
            arguments["min_duration_minutes"] = 30
        if period is not None:
            start, end, _label = period
            arguments.update({"start_date": start.isoformat(), "end_date": end.isoformat()})
        return {"tool_name": "get_last_workout", "arguments": arguments}

    if activity_type is not None and period is not None:
        return _fallback_plan(
            f"I can summarize {activity_type} workouts for that period, but I need to know "
            "whether you want a count, distance, duration, or energy.",
            "clarification_needed",
        )

    return None
