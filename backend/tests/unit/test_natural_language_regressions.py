"""Regression contracts for natural-language chat reliability defects.

These tests use a synthetic profile and template payloads so they do not depend
on a personal export or a live model.  Each assertion captures wording that
previously changed a user's requested metric, range, count, or granularity.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.data_profile import DataProfile
from app.llm.followups import FollowupContext, followup_disambiguation
from app.llm.local_planner import plan_local_question
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


def test_unsupported_pace_ranking_is_not_substituted_with_duration(profile: DataProfile) -> None:
    assert plan_local_question("Top runs by pace", profile) is None


def test_metric_comparison_is_not_substituted_with_workout_comparison(
    profile: DataProfile,
) -> None:
    assert (
        plan_local_question("Compare resting heart rate this month vs last month", profile) is None
    )


def test_fresh_question_with_activity_is_not_mistaken_for_ambiguous_followup() -> None:
    contexts = [
        FollowupContext("dataset-1", "get_trend", {}, label="Resting heart rate"),
        FollowupContext("dataset-1", "get_period_summary", {}, label="Training volume"),
    ]

    assert followup_disambiguation("Show all activity trends", contexts, "dataset-1") is None
    assert followup_disambiguation("How is my fitness", contexts, "dataset-1") is None


@pytest.mark.parametrize(
    ("tool_name", "payload", "required_fact_keys"),
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
                ],
            },
            {"title", "rows"},
        ),
        (
            "get_trend",
            {
                "title": "Steps in June 2026",
                "metric_label": "Steps",
                "metric_unit": "count",
                "granularity": "day",
                "series": [{"bucket": "2026-06-01", "value": 8123}],
            },
            {"metric_label", "metric_unit", "granularity", "series"},
        ),
        (
            "get_period_summary",
            {
                "title": "June 2026",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "metrics": [{"label": "Workouts", "value": 4, "unit": "count"}],
            },
            {"period_start", "period_end", "metrics"},
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
            },
            {"this_period_label", "last_period_label", "metrics"},
        ),
    ],
)
def test_narration_projection_retains_facts_for_non_workout_templates(
    tool_name: str,
    payload: dict[str, object],
    required_fact_keys: set[str],
) -> None:
    facts = narration_projection("Synthetic regression question", tool_name, payload)["facts"]

    assert isinstance(facts, dict)
    assert required_fact_keys <= facts.keys()
