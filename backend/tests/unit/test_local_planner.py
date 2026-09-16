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
        "arguments": {"activity_type": "Running", "min_duration_minutes": 30},
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


def test_plans_top_running_workouts_by_distance() -> None:
    plan = plan_local_question("Top running workouts by distance", _profile())

    assert plan is not None
    assert plan["tool_name"] == "get_top_workouts"
    assert plan["arguments"]["metric"] == "distance"


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


def test_period_and_activity_matching_use_explicit_boundaries() -> None:
    """Last year is a prior calendar year and prose substrings are not workouts."""
    last_year = plan_local_question("resting heart rate last year", _profile())
    assert last_year is not None
    assert last_year["arguments"]["start_date"] == "2025-01-01"
    assert last_year["arguments"]["end_date"] == "2025-12-31"
    assert plan_local_question("Show my top brunch runs", _profile()) is None
    assert plan_local_question("my longest cyclone ride", _profile()) is None


def test_week_comparison_uses_monday_based_ranges() -> None:
    plan = plan_local_question("compare my runs this week and last week", _profile())
    assert plan is not None
    assert plan["arguments"]["this_start"] == "2026-06-15"
    assert plan["arguments"]["last_start"] == "2026-06-08"


def test_preserves_explicit_top_n_dates_and_daily_trend_granularity() -> None:
    ranking = plan_local_question("Top 10 cycling workouts by duration this year", _profile())
    assert ranking is not None
    assert ranking["arguments"]["n"] == 10
    assert ranking["arguments"]["start_date"] == "2026-01-01"

    trend = plan_local_question("Plot steps by day for June 2026", _profile())
    assert trend == {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": "steps",
            "granularity": "day",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
    }


def test_scopes_summaries_and_latest_workouts_to_explicit_constraints() -> None:
    summary = plan_local_question("Show running volume last year", _profile())
    assert summary == {
        "tool_name": "get_period_summary",
        "arguments": {
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "activity_type": "Running",
        },
    }
    latest = plan_local_question("Show my last run in May 2025", _profile())
    assert latest == {
        "tool_name": "get_last_workout",
        "arguments": {
            "activity_type": "Running",
            "start_date": "2025-05-01",
            "end_date": "2025-05-31",
        },
    }
    assert plan_local_question("Show my last workout", _profile()) == {
        "tool_name": "get_last_workout",
        "arguments": {},
    }


def test_returns_an_honest_fallback_for_unsupported_requested_metrics() -> None:
    assert plan_local_question("Top runs by pace", _profile()) == {
        "tool_name": "get_fallback_answer",
        "arguments": {
            "text": "Ranking workouts by pace is not supported yet. "
            "I can rank them by distance, duration, heart rate, or energy."
        },
    }
    comparison_question = "Compare resting heart rate this month vs last month"
    comparison = plan_local_question(comparison_question, _profile())
    assert comparison == {
        "tool_name": "get_fallback_answer",
        "arguments": {
            "text": "Comparing health metrics between periods is not supported yet. "
            "I can show a trend for that metric instead."
        },
    }
