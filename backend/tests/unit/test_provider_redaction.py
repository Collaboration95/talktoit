"""Provider projections must not leak raw health data or local metadata."""

from __future__ import annotations

from app.llm.answer_facts import deterministic_narrative, narration_facts
from app.llm.provider_projection import narration_projection, planning_projection


def test_narration_projection_is_an_allowlist() -> None:
    projected = narration_projection(
        "How was my run?",
        "get_last_workout",
        {
            "activity_type": "Running",
            "duration_minutes": 42.6,
            "gps_route": {"points": [[1.2, 3.4]]},
            "file_path": "/private/health/export.xml",
            "metadata": {"serial": "device-secret"},
            "source_path": "/private/health/route.gpx",
            "secret": "token",
        },
    )

    assert projected == {
        "projection_version": "v2",
        "question": "How was my run?",
        "tool_name": "get_last_workout",
        "facts": {
            "activity_type": "Running",
            "duration": {"value": 43, "unit": "min"},
        },
    }


def test_workout_facts_are_unit_aware_and_preserve_missing_measurements() -> None:
    facts = narration_facts(
        "workout_card",
        {
            "activity_type": "Running",
            "date": "2026-06-08T20:08:48+08:00",
            "duration_minutes": 61.51,
            "distance_meters": 10020.4,
            "distance_unit": "m",
            "avg_heart_rate": 157.2,
            "max_heart_rate": None,
            "energy_burned_kj": 886.9,
            "gps_route": {"coordinates": [[103.8, 1.3]]},
            "workout_fingerprint": "private",
        },
    )

    assert facts == {
        "activity_type": "Running",
        "date": "2026-06-08T20:08:48+08:00",
        "duration": {"value": 62, "unit": "min"},
        "distance": {"value": 10.0, "unit": "km"},
        "average_heart_rate": {"value": 157, "unit": "bpm"},
        "max_heart_rate": {"value": None, "unit": "bpm"},
        "energy": {"value": 887, "unit": "kJ"},
    }


def test_each_success_template_projects_bounded_useful_facts() -> None:
    ranked = narration_facts(
        "ranked_list",
        {
            "title": "Top runs by distance",
            "rows": [
                {"rank": 1, "label": "Running — 2026-06-10", "value": 10.04, "unit": "km"},
                {"rank": 2, "label": "Running — 2026-06-09", "value": 5.01, "unit": "km"},
            ],
            "database_rows": [{"source_name": "private-device"}],
        },
    )
    trend = narration_facts(
        "trend_chart",
        {
            "title": "Steps Trend",
            "metric_label": "Steps",
            "metric_unit": "count",
            "granularity": "day",
            "series": [
                {"bucket": f"2026-06-{day:02d}", "value": day * 1000.4 if day != 3 else None}
                for day in range(1, 12)
            ],
            "raw_records": "not allowed",
        },
    )
    summary = narration_facts(
        "period_summary",
        {
            "title": "June 2026",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "metrics": [{"label": "Total Distance", "value": 12.34, "unit": "km"}],
        },
    )
    comparison = narration_facts(
        "comparison",
        {
            "title": "June vs May",
            "this_period_label": "June 2026",
            "last_period_label": "May 2026",
            "metrics": [
                {
                    "label": "Total Distance",
                    "this_value": 12.34,
                    "last_value": 10.04,
                    "delta": 2.3,
                    "unit": "km",
                    "direction": "up",
                }
            ],
        },
    )

    assert ranked["rows"][0]["value"] == 10.0
    assert len(trend["representative_points"]) == 8
    assert trend["bucket_count"] == 11
    assert trend["missing_bucket_count"] == 1
    assert summary["period_start"] == "2026-06-01"
    assert summary["metrics"] == [{"label": "Total Distance", "value": 12.3, "unit": "km"}]
    assert comparison["metrics"] == [
        {
            "label": "Total Distance",
            "this_value": 12.3,
            "last_value": 10.0,
            "delta": 2.3,
            "unit": "km",
            "direction": "up",
        }
    ]


def test_fallback_and_unknown_templates_never_produce_provider_facts() -> None:
    payload = {"text": "This stays local", "question": "private question", "secret": "no"}
    assert narration_facts("fallback", payload) == {}
    assert narration_facts("future_template", payload) == {}
    assert (
        narration_projection(
            "private question", "get_last_workout", payload, template_id="fallback"
        )["facts"]
        == {}
    )
    assert deterministic_narrative("fallback", {}) == (
        "I found the matching data in your local health database."
    )


def test_planning_projection_contains_only_question_and_compact_context() -> None:
    projected = planning_projection("Find a workout", "Coverage: 2024-01-01 to 2024-02-01")
    assert projected == {
        "projection_version": "v1",
        "question": "Find a workout",
        "dataset_context": "Coverage: 2024-01-01 to 2024-02-01",
    }
