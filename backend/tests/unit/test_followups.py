"""Supported follow-ups resolve exclusively from structured local facts."""

from __future__ import annotations

from app.llm.followups import FollowupContext, resolve_followup


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
