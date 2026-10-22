"""Bounded sleep vocabulary and whole-request date consumption regressions."""

from datetime import date

import pytest

from app.db.data_profile import DataProfile
from app.llm.local_planner import is_sleep_question, plan_local_question
from app.llm.provider_projection import narration_projection, planning_projection

ALIASES = (
    "NREM",
    "non-REM",
    "non REM",
    "nonREM",
    "non-rapid-eye-movement",
    "non rapid eye movement",
    "nonrapid eye movement",
    "nonrapid-eye-movement",
    "rapid eye movement",
    "rapid-eye-movement",
    "REM",
    "stages",
    "categories",
    "asleep",
    "awake",
    "in-bed",
    "deep",
    "core",
    "light",
)


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("sleep", ["", " sleep"])
def test_known_stage_aliases_share_local_and_projection_boundary(alias, sleep):
    question = f"How much {alias}{sleep} did I get from 2026-06-01 to 2026-06-07"
    profile = DataProfile(first_date=None, latest_date=None, workout_types=(), metrics=())
    assert is_sleep_question(question)
    plan = plan_local_question(question, profile)
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "unsupported"
    assert "coverage" in plan["arguments"]["text"]
    assert "Show daily sleep last week" in plan["arguments"]["text"]
    with pytest.raises(ValueError, match="remain local"):
        planning_projection(question, "synthetic metadata")
    with pytest.raises(ValueError, match="remain local"):
        narration_projection(question, "get_trend", {"metric_label": "Steps", "series": []})


@pytest.mark.parametrize(
    "fragment",
    [
        "on 1 June 2026",
        "1 June 2026",
        "1\u20137 June 2026",
        "1-7 June 2026",
        "on the 1st of June 2026",
        "1st June 2026",
        "Monday June 2026",
        "on Monday in June 2026",
        "only 1 June 2026",
        "on 2026-06-01 in June 2026",
        "1 from 2026-06-01 to 2026-06-07",
        "Monday last week",
        "7 this month",
        "2025 during June 2026",
        "on June 2026",
        "in June 2026 on Monday",
    ],
)
def test_date_fragments_are_never_discarded(fragment):
    profile = DataProfile(
        first_date=date(2026, 6, 1),
        latest_date=date(2026, 7, 1),
        workout_types=(),
        metrics=("Sleep",),
    )
    plan = plan_local_question(f"Show daily sleep {fragment}", profile)
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"


@pytest.mark.parametrize(
    "question",
    [
        "Show my last run",
        "Compare steps from 2026-06-01 to 2026-06-07 vs 2026-05-25 to 2026-05-31",
        "Summarize my training",
        "Remember my longest workout",
        "Show my light run last week",
    ],
)
def test_other_questions_still_allow_provider_projections(question):
    assert not is_sleep_question(question)
    assert planning_projection(question, "synthetic metadata")["question"] == question
    assert (
        narration_projection(question, "get_trend", {"metric_label": "Steps"})["question"]
        == question
    )
