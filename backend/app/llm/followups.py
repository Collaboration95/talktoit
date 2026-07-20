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
    if "compare" not in lower or "prior period" not in lower:
        return None
    if context.tool_name != "get_period_summary":
        return None
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
