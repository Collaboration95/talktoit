"""Supported follow-ups resolve exclusively from structured local facts."""

from __future__ import annotations

from app.llm.followups import FollowupContext, followup_disambiguation, resolve_followup


def test_compare_to_prior_period_resolves_from_one_active_context() -> None:
    result = resolve_followup(
        "Compare that to the prior period",
        [
            FollowupContext(
                "ds_one",
                "get_period_summary",
                {"start_date": "2024-02-01", "end_date": "2024-02-07"},
            )
        ],
        "ds_one",
    )
    assert result is not None
    assert result["tool_name"] == "get_comparison"
    assert result["arguments"]["last_start"] == "2024-01-25"


def test_ambiguous_or_stale_context_never_resolves() -> None:
    context = FollowupContext(
        "ds_old", "get_period_summary", {"start_date": "2024-02-01", "end_date": "2024-02-07"}
    )
    assert resolve_followup("Compare that to prior period", [context], "ds_new") is None
    assert resolve_followup("Compare that to prior period", [context, context], "ds_old") is None


def test_regroup_trend_and_restrict_ranked_workouts_use_structured_arguments() -> None:
    trend = resolve_followup(
        "Group that by week",
        [
            FollowupContext(
                "ds_one",
                "get_trend",
                {
                    "metric_id": "HKQuantityTypeIdentifierStepCount",
                    "granularity": "day",
                    "start_date": "2024-02-01",
                    "end_date": "2024-02-07",
                },
            )
        ],
        "ds_one",
    )
    ranked = resolve_followup(
        "Show only running",
        [
            FollowupContext(
                "ds_one", "get_top_workouts", {"activity_type": "Cycling", "metric": "distance"}
            )
        ],
        "ds_one",
    )
    assert trend == {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": "HKQuantityTypeIdentifierStepCount",
            "granularity": "week",
            "start_date": "2024-02-01",
            "end_date": "2024-02-07",
        },
    }
    assert ranked is not None
    assert ranked["arguments"]["activity_type"] == "Running"


def test_ambiguous_references_return_concise_local_turn_choices() -> None:
    contexts = [
        FollowupContext("ds_one", "get_trend", {}, "tr_one", "Show steps"),
        FollowupContext("ds_one", "get_trend", {}, "tr_two", "Show resting HR"),
    ]

    assert followup_disambiguation("Group that by week", contexts, "ds_one") == (
        "Which result should I use? Choose one: Show steps; Show resting HR."
    )
    assert followup_disambiguation("Compare that", [], "ds_one") == (
        "I could not find a current-dataset result to use for that follow-up."
    )
