"""Regression contracts for natural-language chat reliability defects.

These tests use a synthetic profile and template payloads so they do not depend
on a personal export or a live model.  Each assertion captures wording that
previously changed a user's requested metric, range, count, or granularity.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from app.db.data_profile import DataProfile
from app.db.schema import SQL_CREATE_TABLES
from app.llm.followups import FollowupContext, followup_disambiguation
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_projection import narration_projection


@pytest.fixture
def profile() -> DataProfile:
    """A stable synthetic data profile used for relative-date interpretation."""
    return DataProfile(
        first_date=date(2025, 1, 1),
        latest_date=date(2026, 6, 30),
        workout_types=("Running", "Cycling", "Traditional Strength Training"),
        metrics=("Resting HR", "Steps"),
    )


def test_steps_daily_month_request_keeps_metric_and_granularity(profile: DataProfile) -> None:
    assert plan_local_question("Plot steps by day for June 2026", profile) == {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": "steps",
            "granularity": "day",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
    }


def test_top_n_and_year_scope_are_not_replaced_with_defaults(profile: DataProfile) -> None:
    assert plan_local_question("Top 10 cycling workouts by duration this year", profile) == {
        "tool_name": "get_top_workouts",
        "arguments": {
            "activity_type": "Cycling",
            "metric": "duration",
            "n": 10,
            "start_date": "2026-01-01",
            "end_date": "2026-06-30",
        },
    }


def test_daily_resting_hr_request_is_not_silently_coarsened(profile: DataProfile) -> None:
    assert plan_local_question("Show my resting heart rate daily this month", profile) == {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": "HKQuantityTypeIdentifierRestingHeartRate",
            "granularity": "day",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
    }


def test_unsupported_pace_ranking_does_not_create_a_duration_plan(profile: DataProfile) -> None:
    assert plan_local_question("Top runs by pace", profile) == {
        "tool_name": "get_fallback_answer",
        "arguments": {
            "text": "Ranking workouts by pace is not supported yet. "
            "I can rank them by distance, duration, heart rate, or energy."
        },
    }


def test_metric_comparison_does_not_create_a_workout_comparison_plan(
    profile: DataProfile,
) -> None:
    assert plan_local_question("Compare resting heart rate this month vs last month", profile) == {
        "tool_name": "get_fallback_answer",
        "arguments": {
            "text": "Comparing health metrics between periods is not supported yet. "
            "I can show a trend for that metric instead."
        },
    }


@pytest.mark.parametrize(
    "question",
    ["Top runs by pace", "Compare resting heart rate this month vs last month"],
)
async def test_unsupported_intent_returns_an_honest_terminal_response(
    profile: DataProfile, question: str
) -> None:
    """Unsupported requests must not execute a different supported analysis.

    This is deliberately an orchestrator contract rather than only a planner
    assertion: returning ``None`` from a local recognizer is not enough if a
    later stage quietly dispatches a duration ranking or workout comparison.
    """
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(SQL_CREATE_TABLES)
        client = MagicMock()
        orchestrator = ChatOrchestrator(client=client, conn=conn)  # type: ignore[arg-type]

        response = await orchestrator.answer(question, data_profile=profile)

        assert response.template_id == "fallback"
        assert response.metadata.provenance == "fallback"
        assert "not supported" in (response.data["text"] or "").casefold()
        assert response.narrative == ""
    finally:
        conn.close()


def test_fresh_question_with_activity_is_not_mistaken_for_ambiguous_followup() -> None:
    contexts = [
        FollowupContext("dataset-1", "get_trend", {}, label="Resting heart rate"),
        FollowupContext("dataset-1", "get_period_summary", {}, label="Training volume"),
    ]

    assert followup_disambiguation("Show all activity trends", contexts, "dataset-1") is None
    assert followup_disambiguation("How is my fitness", contexts, "dataset-1") is None


@pytest.mark.parametrize(
    ("tool_name", "payload", "required_fact_keys", "collection_key", "max_items"),
    [
        (
            "get_top_workouts",
            {
                "title": "Top running workouts by distance",
                "rows": [
                    {
                        "rank": 1,
                        "label": "5 Jun 2026",
                        "value": 8.5,
                        "unit": "km",
                        "secondary_value": 45.5,
                        "secondary_unit": "min",
                    }
                ]
                * 4,
                "raw_rows": [{"source_path": "/private/health/export.xml"}],
            },
            {"title", "rows"},
            "rows",
            10,
        ),
        (
            "get_trend",
            {
                "title": "Steps in June 2026",
                "metric_label": "Steps",
                "metric_unit": "count",
                "granularity": "day",
                "series": [
                    {"bucket": f"2026-06-{day:02d}", "value": 8_000 + day} for day in range(1, 9)
                ],
                "device_metadata": {"serial": "not-for-provider"},
            },
            {"metric_label", "metric_unit", "granularity", "representative_points"},
            "representative_points",
            8,
        ),
        (
            "get_period_summary",
            {
                "title": "June 2026",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "metrics": [{"label": "Workouts", "value": 4, "unit": "count"}],
                "gps_route": {"coordinates": [[103.8, 1.3]]},
            },
            {"period_start", "period_end", "metrics"},
            "metrics",
            8,
        ),
        (
            "get_comparison",
            {
                "title": "This month vs last month",
                "this_period_label": "June 2026",
                "last_period_label": "May 2026",
                "metrics": [
                    {
                        "label": "Sessions",
                        "this_value": 4,
                        "last_value": 3,
                        "delta": 1,
                        "unit": "count",
                        "direction": "up",
                    }
                ],
                "internal_note": "do not send",
            },
            {"this_period_label", "last_period_label", "metrics"},
            "metrics",
            8,
        ),
    ],
)
def test_narration_projection_retains_facts_for_non_workout_templates(
    tool_name: str,
    payload: dict[str, Any],
    required_fact_keys: set[str],
    collection_key: str,
    max_items: int,
) -> None:
    facts = narration_projection("Synthetic regression question", tool_name, payload)["facts"]

    assert isinstance(facts, dict)
    assert required_fact_keys <= facts.keys()
    assert facts["title"] == payload["title"]
    collection = facts[collection_key]
    assert isinstance(collection, list)
    assert collection
    assert len(collection) <= max_items
    required_item_fields = {
        "rows": {"rank", "label", "value", "unit"},
        "representative_points": {"bucket", "value"},
        "metrics": {"label", "value", "unit"},
    }
    if tool_name == "get_comparison":
        required_item_fields["metrics"] = {
            "label",
            "this_value",
            "last_value",
            "delta",
            "unit",
            "direction",
        }
    for item in collection:
        assert isinstance(item, dict)
        assert required_item_fields[collection_key] <= item.keys()
    assert not _contains_sensitive_key(facts)


def _contains_sensitive_key(value: object) -> bool:
    """Keep raw rows, health-file paths, routes, and device details off-provider."""
    sensitive_keys = {"device_metadata", "gps_route", "internal_note", "raw_rows", "source_path"}
    if isinstance(value, dict):
        return any(
            key in sensitive_keys or _contains_sensitive_key(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
