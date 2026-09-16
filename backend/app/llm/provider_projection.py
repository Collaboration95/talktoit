"""Versioned, allowlisted projections for optional provider messages.

These functions deliberately accept untrusted dictionaries but only emit the
small set of facts a planner or narrator needs.  They are the egress boundary:
callers must not interpolate tool payloads directly into provider messages.
"""

from __future__ import annotations

from typing import Any

from app.llm.answer_facts import NARRATION_FACTS_VERSION, narration_facts

PLANNING_PROJECTION_VERSION = "v1"
NARRATION_PROJECTION_VERSION = NARRATION_FACTS_VERSION

_TOOL_TEMPLATE_IDS = {
    "get_last_workout": "workout_card",
    "get_top_workouts": "ranked_list",
    "get_trend": "trend_chart",
    "get_period_summary": "period_summary",
    "get_comparison": "comparison",
    "get_fallback_answer": "fallback",
}


def planning_projection(question: str, data_context: str) -> dict[str, str]:
    """Return the only user and dataset fields allowed to remote planning."""
    return {
        "projection_version": PLANNING_PROJECTION_VERSION,
        "question": question,
        "dataset_context": data_context,
    }


def narration_projection(
    question: str,
    tool_name: str,
    payload: dict[str, Any],
    *,
    template_id: str | None = None,
) -> dict[str, object]:
    """Return compact template facts, excluding all unrecognised payload keys.

    Tool names remain accepted for compatibility at this LLM boundary.  New
    callers should pass the actual ``template_id`` returned by dispatch: a
    successful tool can legitimately return the terminal fallback template.
    Without it, the stable tool-to-template mapping preserves legacy callers.
    """
    facts = narration_facts(template_id or _TOOL_TEMPLATE_IDS.get(tool_name, ""), payload)
    return {
        "projection_version": NARRATION_PROJECTION_VERSION,
        "question": question,
        "tool_name": tool_name,
        "facts": facts,
    }
