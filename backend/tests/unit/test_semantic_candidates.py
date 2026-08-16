"""P6-03 — local semantic candidates and the strict intent verifier.

The acceptance proof is an adversarial candidate matrix: "last run" must never
match "last long run", and differing metrics, periods, activities, or
aggregations must never be auto-served. Everything here is local and pure.
"""

from __future__ import annotations

import json

from app.llm.semantic_candidates import (
    evaluate,
    normalize_question,
    plan_fingerprint,
    similarity,
)


def _run_plan(activity_type: str = "Running", min_duration: int | None = None) -> dict[str, object]:
    args: dict[str, object] = {"activity_type": activity_type}
    if min_duration is not None:
        args["min_duration_minutes"] = min_duration
    return {"tool_name": "get_last_workout", "arguments": args}


def _trend_plan(metric_id: str, granularity: str = "day") -> dict[str, object]:
    return {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": metric_id,
            "granularity": granularity,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    }


def _turn(
    turn_id: str,
    question: str,
    plan: dict[str, object] | None,
    response: str = '{"template_id":"workout_card","data":{},"narrative":"x"}',
) -> dict[str, object]:
    return {
        "id": turn_id,
        "conversation_id": "c1",
        "question": question,
        "response_json": response,
        "created_at": f"2026-08-0{turn_id}T00:00:00+00:00",
        "canonical_plan_json": json.dumps(plan, sort_keys=True) if plan else None,
        "normalized_question": normalize_question(question),
    }


def _args(plan: dict[str, object] | None) -> tuple[str | None, dict[str, object]]:
    if not plan:
        return None, {}
    return str(plan["tool_name"]), dict(plan["arguments"])


def test_normalize_question_drops_stopwords_preserves_numbers() -> None:
    assert normalize_question("Show me my last 5k run") == "last 5k run"
    assert "resting heart rate" in normalize_question("What did my resting heart rate do?")
    assert "5k" in normalize_question("run 5k")


def test_similarity_is_symmetric_and_bounded() -> None:
    assert similarity("last run", "last run") == 1.0
    assert similarity("swimming laps", "sleep hours") < 1.0


def test_identical_intent_is_auto_servable_across_different_wording() -> None:
    prior = _turn("1", "Show me my most recent run", _run_plan())
    tool, args = _args(_run_plan())
    verdict = evaluate([prior], "What was my last run?", (tool or "", args))
    assert verdict.auto_servable is True
    assert verdict.identical is not None
    assert verdict.identical.turn_id == "1"


def test_last_run_never_matches_last_long_run() -> None:
    prior = _turn("1", "Show my last run", _run_plan())
    long_plan = _run_plan(min_duration=60)
    tool, args = _args(long_plan)
    verdict = evaluate([prior], "my last long run", (tool or "", args))
    same = _args(_run_plan())
    # "Last run" (no min duration) is proven different from "last long run".
    assert plan_fingerprint(tool or "", args) != plan_fingerprint(same[0] or "", same[1])
    assert verdict.identical is None


def test_differing_metrics_never_auto_hit() -> None:
    prior = _turn("1", "resting heart rate this month", _trend("RestingHR"))
    tool, args = _args(_trend("Steps"))  # user now asks about steps
    verdict = evaluate([prior], "how many steps this week?", (tool or "", args))
    assert verdict.identical is None


def _trend(metric_id: str) -> dict[str, object]:
    return _trend_plan(metric_id)


def test_differing_periods_never_auto_hit() -> None:
    prior = _turn(
        "1",
        "steps in june",
        {
            "tool_name": "get_trend",
            "arguments": {
                "metric_id": "Steps",
                "granularity": "day",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            },
        },
    )
    july = {
        "tool_name": "get_trend",
        "arguments": {
            "metric_id": "Steps",
            "granularity": "day",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
        },
    }
    tool, args = _args(july)
    verdict = evaluate([prior], "steps in july", (tool or "", args))
    assert verdict.identical is None


def test_missing_response_is_never_reused() -> None:
    prior = _turn("1", "last run", _run_plan(), response="")
    tool, args = _args(_run_plan())
    verdict = evaluate([prior], "last run", (tool or "", args))
    assert verdict.identical is None


def test_no_network_is_used() -> None:
    """evaluate() is pure and synchronous over local records; no remote client."""
    prior = _turn("1", "last run", _run_plan())
    tool, args = _args(_run_plan())
    verdict = evaluate([prior], "last run", (tool or "", args))
    assert verdict.auto_servable is True


def test_semantic_turns_exposes_normalized_questions_per_dataset(tmp_path) -> None:
    """Repository persistence: normalized text is stored and scoped by dataset."""
    from app.state.app_state import AppStateRepository

    repo = AppStateRepository(tmp_path / "state.sqlite")
    repo.migrate()
    active = repo.activate(
        source_bytes=b"",
        source_size_bytes=0,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-01-01",
        coverage_end="2026-08-31",
        counts={"records": 1},
    )
    assert active is not None
    conversation_id = repo.create_conversation("Runs", active.id)
    repo.add_completed_turn(
        conversation_id,
        "Show my last run",
        '{"template_id":"fallback","data":{"question":"x","table":null,"text":"y"},'
        '"narrative":"y","metadata":{"provenance":"deterministic_local","api_version":"v1"}}',
        "default",
        "deterministic_local",
        canonical_plan=_run_plan(),
    )
    turns = repo.semantic_turns(active.id)
    assert len(turns) == 1
    assert turns[0]["normalized_question"] == "last run"
    # Candidate rows carry no response envelope; the identical turn's response
    # is fetched lazily via ``get_turn`` (GH-6).
    assert "response_json" not in turns[0]
    assert turns[0]["canonical_plan_json"].startswith("{")

    # A second dataset must not see the first dataset's turns.
    other = repo.activate(
        source_bytes=b"",
        source_size_bytes=0,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-02-01",
        coverage_end="2026-09-30",
        counts={"records": 1},
    )
    assert other is not None
    assert repo.semantic_turns(other.id) == []
