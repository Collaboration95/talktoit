"""Synthetic period summaries preserve absent measurements and measured zero."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest

from app.db.data_profile import DataProfile
from app.db.schema import SQL_CREATE_TABLES
from app.llm.answer_facts import deterministic_narrative, narration_facts
from app.llm.orchestrator import ChatOrchestrator
from app.models.chat import ChatResponse


@pytest.mark.parametrize(
    ("workouts", "duration", "distance", "expected"),
    [
        (0, None, None, "No workouts were recorded for the requested period."),
        (1, 0.0, 0.0, "Total Distance: 0.0 km, Total Duration: 0 min"),
        (1, None, None, "Total Distance: unavailable, Total Duration: unavailable"),
        (1, 0.0, None, "Total Distance: unavailable, Total Duration: 0 min"),
        (1, None, 0.0, "Total Distance: 0.0 km, Total Duration: unavailable"),
    ],
)
async def test_period_summary_wording(workouts, duration, distance, expected):
    with duckdb.connect(":memory:") as conn:
        conn.execute(SQL_CREATE_TABLES)
        if workouts:
            conn.execute(
                "INSERT INTO workouts VALUES "
                "(1, 'Running', ?, 'min', 'Synthetic', NULL, NULL, "
                "'2026-06-10 00:00:00', '2026-06-10 00:00:00', '2026-06-10 00:00:00')",
                [duration],
            )
            if distance is not None:
                conn.execute(
                    "INSERT INTO workout_statistics (workout_id, type, sum, unit) "
                    "VALUES (1, 'HKQuantityTypeIdentifierDistanceWalkingRunning', ?, 'm')",
                    [distance],
                )
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=AssertionError("No model calls"))
        response = await ChatOrchestrator(client=client, conn=conn).answer(
            "Show running volume this week",
            data_profile=DataProfile(
                first_date=date(2026, 6, 1),
                latest_date=date(2026, 6, 10),
                workout_types=("Running",),
                metrics=(),
            ),
        )

    assert response.template_id == "period_summary"
    assert response.metadata.provenance == "deterministic_local"
    assert response.data["period_start"] == "2026-06-08"
    assert response.data["period_end"] == "2026-06-10"
    values = {item["label"]: item["value"] for item in response.data["metrics"]}
    assert values["Workouts"] == workouts
    assert values["Total Duration"] == duration
    assert values["Total Distance"] == distance
    assert expected in response.narrative
    assert "None" not in response.narrative
    if workouts:
        assert "No workouts" not in response.narrative
    else:
        assert "Try a wider date range" in response.narrative
    assert ChatResponse.model_validate_json(response.model_dump_json()) == response
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.parametrize(
    "metrics", [[], [{"label": "Workouts", "value": None, "unit": "sessions"}]]
)
def test_missing_summary_does_not_claim_no_workouts(metrics):
    facts = narration_facts("period_summary", {"title": "Training summary", "metrics": metrics})
    narrative = deterministic_narrative("period_summary", facts)
    assert "No workouts" not in narrative
    assert "None" not in narrative
    assert "unavailable" in narrative or "No summary measurements are available" in narrative
