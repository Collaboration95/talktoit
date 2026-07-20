"""Provider projections must not leak raw health data or local metadata."""

from __future__ import annotations

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
        "projection_version": "v1",
        "question": "How was my run?",
        "tool_name": "get_last_workout",
        "facts": {"activity_type": "Running", "duration_minutes": 43},
    }


def test_planning_projection_contains_only_question_and_compact_context() -> None:
    projected = planning_projection("Find a workout", "Coverage: 2024-01-01 to 2024-02-01")
    assert projected == {
        "projection_version": "v1",
        "question": "Find a workout",
        "dataset_context": "Coverage: 2024-01-01 to 2024-02-01",
    }
