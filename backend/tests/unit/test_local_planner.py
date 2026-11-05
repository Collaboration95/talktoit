"""Tests for the deterministic fallback planner."""

from __future__ import annotations

from datetime import date

import pytest

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

    explicit_count = plan_local_question("Which top 10 cycling workouts by duration?", _profile())
    assert explicit_count is not None
    assert explicit_count["arguments"]["n"] == 10

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
            "Try: Top 5 longest runs this year.",
            "reason": "unsupported",
        },
    }
    comparison_question = "Compare resting heart rate this month vs last month"
    comparison = plan_local_question(comparison_question, _profile())
    assert comparison is not None
    assert comparison["tool_name"] == "get_fallback_answer"
    assert comparison["arguments"]["reason"] == "clarification_needed"
    assert "two complete date ranges" in comparison["arguments"]["text"]


def test_does_not_treat_a_period_only_workout_request_as_latest() -> None:
    plan = plan_local_question("Show runs last week", _profile())
    assert plan == {
        "tool_name": "get_fallback_answer",
        "arguments": {
            "text": "I can summarize Running workouts for that period, but I need to know "
            "whether you want a count, distance, duration, or energy.",
            "reason": "clarification_needed",
        },
    }


@pytest.mark.parametrize(
    "clause",
    [
        "from June 2026 to July 2026",
        "between June 2026 and July 2026",
        "in June 2026 and July 2026",
        "in June 2026 or July 2026",
        "in June 2026 and last week",
        "last week and this week",
        "this month except last week",
        "last week from 2026-06-01 to 2026-06-07",
        "from 2026-06-01 to 2026-06-07 and last week",
        "from June 2026",
        "since June 2026",
        "before June 2026",
        "in June 2026 through July",
        "in June 0000",
    ],
)
def test_sleep_requires_one_complete_supported_date_clause(clause):
    plan = plan_local_question(f"Show daily sleep {clause}", _profile())
    assert plan is not None
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"
    assert "date range" in plan["arguments"]["text"]


@pytest.mark.parametrize(
    "clause,start,end",
    [
        ("from 2026-06-01 to 2026-07-31", "2026-06-01", "2026-07-31"),
        ("from 2026-06-01 through 2026-06-07", "2026-06-01", "2026-06-07"),
        ("between 2026-06-01 to 2026-06-07", "2026-06-01", "2026-06-07"),
        ("from 1\u20137 June 2026", "2026-06-01", "2026-06-07"),
        ("from June 1\u20137, 2026", "2026-06-01", "2026-06-07"),
        ("in June 2026", "2026-06-01", "2026-06-30"),
        ("for June 2026", "2026-06-01", "2026-06-30"),
        ("during June 2026", "2026-06-01", "2026-06-30"),
        ("June 2026", "2026-06-01", "2026-06-30"),
        ("last week", "2026-06-08", "2026-06-14"),
        ("this week", "2026-06-15", "2026-06-17"),
        ("last month", "2026-05-01", "2026-05-31"),
        ("this month", "2026-06-01", "2026-06-17"),
        ("last year", "2025-01-01", "2025-12-31"),
        ("this year", "2026-01-01", "2026-06-17"),
        ("year to date", "2026-01-01", "2026-06-17"),
    ],
)
def test_sleep_retains_supported_explicit_relative_and_month_scopes(clause, start, end):
    plan = plan_local_question(f"Show daily sleep {clause}.", _profile())
    assert plan == {
        "tool_name": "get_sleep_trend",
        "arguments": {"start_date": start, "end_date": end, "granularity": "day"},
    }


@pytest.mark.parametrize(
    "granularity,expected", [("daily", "day"), ("weekly", "week"), ("monthly", "month")]
)
def test_sleep_coverage_wording_keeps_its_measurement(granularity, expected):
    plan = plan_local_question(
        f"Show {granularity} sleep interval coverage including awake and in-bed records last week",
        _profile(),
    )
    assert plan == {
        "tool_name": "get_sleep_trend",
        "arguments": {
            "start_date": "2026-06-08",
            "end_date": "2026-06-14",
            "granularity": expected,
        },
    }


@pytest.mark.parametrize(
    "prompt,tool_name,extra",
    [
        ("Show daily steps", "get_trend", {"metric_id": "steps", "granularity": "day"}),
        ("Show running volume", "get_period_summary", {"activity_type": "Running"}),
        (
            "Top 3 longest runs",
            "get_top_workouts",
            {"activity_type": "Running", "metric": "duration", "n": 3},
        ),
        ("Show my last run", "get_last_workout", {"activity_type": "Running"}),
    ],
)
@pytest.mark.parametrize(
    "clause,start,end",
    [
        ("from 2026-06-01 to 2026-06-07", "2026-06-01", "2026-06-07"),
        ("from 2026-06-01 through 2026-06-07", "2026-06-01", "2026-06-07"),
        ("between 2026-06-01 and 2026-06-07", "2026-06-01", "2026-06-07"),
        ("from 2024-02-29 to 2024-02-29", "2024-02-29", "2024-02-29"),
        ("from 1\u20137 June 2026", "2026-06-01", "2026-06-07"),
        ("from June 1\u20137, 2026", "2026-06-01", "2026-06-07"),
    ],
)
def test_general_plans_preserve_complete_explicit_ranges(
    prompt, tool_name, extra, clause, start, end
):
    plan = plan_local_question(f"{prompt} {clause}.", _profile())
    assert plan == {
        "tool_name": tool_name,
        "arguments": {**extra, "start_date": start, "end_date": end},
    }


@pytest.mark.parametrize(
    "prompt", ["Show daily steps", "Show running volume", "Top 3 runs", "Show my last run"]
)
@pytest.mark.parametrize(
    "clause",
    [
        "from 2026-06-07 to 2026-06-01",
        "from 2026-02-29 to 2026-03-07",
        "from 2026-00-01 to 2026-06-07",
        "from 0000-06-01 to 2026-06-07",
        "from 2026-6-1 to 2026-6-7",
        "from 2026-06-01",
        "since 2026-06-01",
        "before 2026-06-07",
        "on 2026-06-01",
        "2026-06-01 to 2026-06-07",
        "from June 2026 to July 2026",
        "between June 2026 and July 2026",
        "in June 2026 and July 2026",
        "in June 2026 or July 2026",
        "in June 2026 and last week",
        "last week and this week",
        "this month except last week",
        "last week from 2026-06-01 to 2026-06-07",
        "from 2026-06-01 to 2026-06-07 and last week",
        "from 2026-06-01 to 2026-06-07 and 2026-06-09",
        "from 2026-06-01 to 2026-06-07 except weekends",
        "in June 0000",
        "in December 9999",
        "last 7 days",
        "last ten days",
        "last weekend",
        "on Monday",
        "06/01 to 06/07",
        "yesterday",
    ],
)
def test_general_plans_reject_invalid_incomplete_or_unsupported_date_scopes(prompt, clause):
    plan = plan_local_question(f"{prompt} {clause}", _profile())
    assert plan is not None
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"
    assert "date range" in plan["arguments"]["text"]


@pytest.mark.parametrize(
    "metrics", ["steps and HRV", "resting heart rate and steps", "HRV and active energy"]
)
def test_single_metric_trends_do_not_silently_drop_other_metrics(metrics):
    plan = plan_local_question(f"Show daily {metrics} last week", _profile())
    assert plan is not None
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"
    assert "one metric" in plan["arguments"]["text"]


@pytest.mark.parametrize(
    "latest,start,end",
    [
        (date(2020, 2, 12), "2020-02-03", "2020-02-09"),
        (date(2026, 6, 17), "2026-06-08", "2026-06-14"),
    ],
)
def test_general_relative_dates_remain_anchored_to_the_dataset(latest, start, end):
    plan = plan_local_question("Show daily steps last week", _profile(latest))
    assert plan is not None
    assert plan["arguments"]["start_date"] == start
    assert plan["arguments"]["end_date"] == end


def test_polite_may_is_not_a_month_constraint():
    assert plan_local_question("May I see my last run?", _profile()) == {
        "tool_name": "get_last_workout",
        "arguments": {"activity_type": "Running"},
    }


@pytest.mark.parametrize(
    "clause",
    [
        "this week and last month",
        "this week and this week",
        "this month vs last month except weekends",
        "this week and last week from 2026-06-01 to 2026-06-07",
        "from 2026-06-01 to 2026-06-07 and last week",
    ],
)
def test_workout_comparisons_do_not_discard_unsupported_date_constraints(clause):
    plan = plan_local_question(f"Compare my running {clause}", _profile())
    assert plan is not None
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"


@pytest.mark.parametrize("clause", ["this week to last week", "last week and this week"])
def test_equivalent_relative_workout_comparisons_remain_supported(clause):
    plan = plan_local_question(f"Compare my running {clause}", _profile())
    assert plan is not None
    assert plan["tool_name"] == "get_comparison"
    assert plan["arguments"]["this_start"] == "2026-06-15"
    assert plan["arguments"]["last_start"] == "2026-06-08"
