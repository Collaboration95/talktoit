"""Deterministic, privacy-safe follow-up planning from structured local intent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class FollowupContext:
    """Minimal persisted context required to resolve a supported reference."""

    dataset_version_id: str
    tool_name: str
    arguments: dict[str, Any]
    turn_id: str | None = None
    label: str | None = None


def resolve_followup(
    question: str,
    contexts: list[FollowupContext],
    active_dataset_version_id: str | None,
) -> dict[str, Any] | None:
    """Resolve supported references without reading transcript text or payloads.

    A result is returned only for one unambiguous prior context in the active
    dataset.  Everything else stays a normal fresh question.
    """
    if active_dataset_version_id is None:
        return None
    candidates = [item for item in contexts if item.dataset_version_id == active_dataset_version_id]
    if len(candidates) != 1:
        return None
    context = candidates[0]
    lower = question.casefold()
    if "compare" in lower and "prior period" in lower and context.tool_name == "get_period_summary":
        try:
            start = date.fromisoformat(str(context.arguments["start_date"]))
            end = date.fromisoformat(str(context.arguments["end_date"]))
        except (KeyError, TypeError, ValueError):
            return None
        duration = end - start
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - duration
        return {
            "tool_name": "get_comparison",
            "arguments": {
                "this_start": start.isoformat(),
                "this_end": end.isoformat(),
                "last_start": previous_start.isoformat(),
                "last_end": previous_end.isoformat(),
                "this_label": f"{start.isoformat()} to {end.isoformat()}",
                "last_label": f"{previous_start.isoformat()} to {previous_end.isoformat()}",
            },
        }
    if context.tool_name == "get_trend" and ("group" in lower or "by week" in lower):
        arguments = dict(context.arguments)
        arguments["granularity"] = "month" if "month" in lower else "week"
        return {"tool_name": "get_trend", "arguments": arguments}
    if context.tool_name == "get_top_workouts" and "only" in lower:
        activity_type = _activity_type_from_question(lower)
        if activity_type is None:
            return None
        arguments = dict(context.arguments)
        arguments["activity_type"] = activity_type
        return {"tool_name": "get_top_workouts", "arguments": arguments}
    return None


def followup_disambiguation(
    question: str,
    contexts: list[FollowupContext],
    active_dataset_version_id: str | None,
) -> str | None:
    """Return a concise local choice prompt for ambiguous supported references.

    Only persisted plan labels and user-written questions are used here.  Raw
    result payloads, route geometry, and metadata never enter this message or
    a provider prompt.
    """
    lower = question.casefold()
    if not any(
        phrase in lower
        for phrase in ("that", "it", "prior period", "group", "only", "open selected")
    ):
        return None
    if active_dataset_version_id is None:
        return "Start with a current-dataset result, then ask the follow-up again."
    candidates = [item for item in contexts if item.dataset_version_id == active_dataset_version_id]
    if not candidates:
        return "I could not find a current-dataset result to use for that follow-up."
    if len(candidates) == 1:
        return None
    choices = [item.label or item.tool_name.replace("_", " ") for item in candidates[-3:]]
    return "Which result should I use? Choose one: " + "; ".join(choices) + "."


def _activity_type_from_question(question: str) -> str | None:
    """Map a deliberately small safe activity vocabulary to tool arguments."""
    if "run" in question or "jog" in question:
        return "Running"
    if "cycl" in question or "bike" in question:
        return "Cycling"
    if any(word in question for word in ("gym", "strength", "weight")):
        return "TraditionalStrengthTraining"
    return None
