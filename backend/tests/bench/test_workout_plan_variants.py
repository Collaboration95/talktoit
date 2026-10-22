"""Real production plans on one parity-verified copy of the committed tiny fixture."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from app.db import queries
from app.ingest.coordinator import ingest_v2

VARIANTS = {
    "latest_broad",
    "latest_selective",
    "ranked_broad",
    "ranked_selective",
    "paged_broad_first",
    "paged_broad_next",
    "paged_date_first",
    "paged_date_next",
    "paged_type_first",
    "paged_type_next",
    "paged_source_first",
    "paged_source_next",
    "paged_selective_first",
    "paged_selective_next",
}
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/sample.xml"


def test_actual_helpers_filters_cursor_order_nulls_and_real_plans(monkeypatch):
    from app.bench.workload import workout_plan_variants

    calls = {"latest": [], "ranked": [], "paged": []}
    for name, helper in (
        ("latest", "get_last_workout"),
        ("ranked", "get_top_workouts"),
        ("paged", "get_workout_collection"),
    ):
        actual = getattr(queries, helper)

        def observe(conn, *args, _actual=actual, _name=name, **kwargs):
            calls[_name].append(dict(kwargs))
            return _actual(conn, *args, **kwargs)

        monkeypatch.setattr(queries, helper, observe)
    with duckdb.connect(":memory:") as conn:
        stats = ingest_v2(FIXTURE, conn, n_workers=1)
        assert tuple(
            stats[key]
            for key in (
                "records",
                "record_metadata",
                "hrv_beats",
                "workouts",
                "workout_events",
                "workout_statistics",
                "workout_routes",
                "workout_metadata",
                "activity_summaries",
            )
        ) == (40, 7, 7, 3, 6, 8, 2, 12, 5)
        runs = workout_plan_variants(conn)
    assert set(runs) == VARIANTS
    assert len(calls["latest"]) == len(calls["ranked"]) == 2
    assert len(calls["paged"]) == 10
    assert all("EXPLAIN_ANALYZE" in run.raw_plan for run in runs.values())
    assert all(run.evidence.success for run in runs.values())
    assert all(run.evidence.operator_cardinality is None for run in runs.values())
    first = runs["paged_broad_first"].result
    second = runs["paged_broad_next"].result
    assert [row[0] for row in first + second] == [3, 2]
    assert first[0][2] > second[0][2]
    assert first[0][7] == 45000
    assert second[0][7] is None  # The strength workout has no measured distance.
    assert runs["latest_broad"].result.workout_id == first[0][0]
    assert runs["latest_selective"].result.workout_id == first[0][0]
    paged = calls["paged"]
    for index, scope in enumerate(("broad", "date", "type", "source", "selective")):
        original = runs[f"paged_{scope}_first"].result
        following = runs[f"paged_{scope}_next"].result
        assert original  # Scope is anchored to an actual fixture result.
        cursor = original[-1]
        first_call, next_call = paged[index * 2 : index * 2 + 2]
        assert first_call["cursor_date"] is first_call["cursor_id"] is None
        assert (next_call["cursor_date"], next_call["cursor_id"]) == (cursor[2], cursor[0])
        assert not {row[0] for row in original} & {row[0] for row in following}
        if scope != "broad":
            assert following == []  # Independent date/type/source filters exclude older rows.
    assert paged[0]["activity_type"] is paged[0]["source"] is None
    assert paged[2]["start"] == paged[2]["end"]
    assert paged[4]["activity_type"] == "Cycling" and paged[4]["source"] is None
    assert paged[6]["source"] == "Strava" and paged[6]["activity_type"] is None
    assert paged[8]["activity_type"] == "Cycling" and paged[8]["source"] == "Strava"
    assert paged[8]["start"] == paged[8]["end"]
    assert calls["latest"][0]["activity_type"] is None
    assert calls["latest"][1]["start"] == calls["latest"][1]["end"]
    assert calls["ranked"][0]["start"] is calls["ranked"][0]["end"] is None
    assert calls["ranked"][1]["start"] == calls["ranked"][1]["end"]
    published = json.dumps({name: run.evidence.model_dump() for name, run in runs.items()})
    for forbidden in (
        "SELECT",
        "EXPLAIN",
        "Strava",
        "Apple Watch",
        "2026-",
        "raw_plan",
        "params",
        str(FIXTURE),
    ):
        assert forbidden not in published


def test_plan_evidence_rejects_unstructured_or_invented_operator_statistics():
    from app.bench.report import PlanEvidence

    evidence = PlanEvidence(success=True, result_rows=1)
    assert evidence.model_dump() == {
        "success": True,
        "result_rows": 1,
        "operator_cardinality": None,
    }
    for field in ("sql", "params", "raw_plan", "path", "rows", "question"):
        with pytest.raises(ValidationError):
            PlanEvidence.model_validate({**evidence.model_dump(), field: "PRIVATE_SENTINEL"})
    with pytest.raises(ValidationError):
        PlanEvidence(success=True, result_rows=-1)
    with pytest.raises(ValidationError):
        PlanEvidence(success=True, result_rows=1, operator_cardinality=100)
