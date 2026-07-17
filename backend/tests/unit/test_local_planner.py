"""Tests for the deterministic fallback planner."""

from __future__ import annotations

from datetime import date

from app.db.data_profile import DataProfile
from app.llm.local_planner import plan_local_question


def _profile(latest_date: date | None = date(2026, 6, 17)) -> DataProfile:
    return DataProfile(
        first_date=date(2025, 12, 17) if latest_date else None,
        latest_date=latest_date,
        workout_types=("Running", "Cycling", "Traditional Strength Training"),
        metrics=("Resting HR", "Steps"),
    )


def test_plans_last_run() -> None:
    assert plan_local_question("Show me my last long run", _profile()) == {
        "tool_name": "get_last_workout",
        "arguments": {"activity_type": "Running"},
    }


def test_plans_highest_heart_rate_gym_session_last_month() -> None:
    plan = plan_local_question(
        "Which gym session had the highest heart rate last month?", _profile()
    )

    assert plan == {
        "tool_name": "get_top_workouts",
        "arguments": {
            "activity_type": "TraditionalStrengthTraining",
            "metric": "avg_hr",
            "n": 1,
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
        },
    }


def test_plans_longest_runs_this_year() -> None:
    plan = plan_local_question("Top 5 longest runs this year", _profile())

    assert plan is not None
    assert plan["tool_name"] == "get_top_workouts"
    assert plan["arguments"]["metric"] == "duration"
    assert plan["arguments"]["start_date"] == "2026-01-01"
    assert plan["arguments"]["end_date"] == "2026-06-17"


def test_plans_resting_heart_rate_trend() -> None:
    plan = plan_local_question("Show my resting heart rate trend this year", _profile())

    assert plan is not None
    assert plan["tool_name"] == "get_trend"
    assert plan["arguments"]["granularity"] == "week"
    assert plan["arguments"]["metric_id"] == "HKQuantityTypeIdentifierRestingHeartRate"


def test_plans_training_volume_last_week() -> None:
    plan = plan_local_question("How was my training volume last week?", _profile())

    assert plan == {
        "tool_name": "get_period_summary",
        "arguments": {"start_date": "2026-06-08", "end_date": "2026-06-14"},
    }


def test_plans_running_month_comparison() -> None:
    plan = plan_local_question("Compare my running this month vs last month", _profile())

    assert plan is not None
    assert plan["tool_name"] == "get_comparison"
    assert plan["arguments"]["activity_type"] == "Running"
    assert plan["arguments"]["this_start"] == "2026-06-01"
    assert plan["arguments"]["last_start"] == "2026-05-01"


def test_returns_none_for_unrecognised_question_or_empty_database() -> None:
    assert plan_local_question("What should I eat?", _profile()) is None
    assert plan_local_question("Show my last run", _profile(latest_date=None)) is None
