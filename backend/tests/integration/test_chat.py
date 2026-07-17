"""Integration tests for the chat endpoint and orchestrator.

The LLM client is replaced with a deterministic stub so tests run without
live API calls. The DuckDB connection is a real in-memory DB seeded from the
synthetic fixture — per ENGINEERING §2.4 (never mock the database).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingest.parser import ingest
from app.llm.orchestrator import ChatOrchestrator
from app.main import create_app

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    ingest(str(FIXTURE), conn)
    return conn


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


def _make_planner_response(tool_name: str, args: dict[str, Any]) -> MagicMock:
    """Build a minimal ChatCompletion mock for the planner turn."""
    message = MagicMock()
    message.tool_calls = None
    message.content = json.dumps({"tool_name": tool_name, "arguments": args})
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_narrative_response(text: str) -> MagicMock:
    """Build a minimal ChatCompletion mock for the narrative turn."""
    message = MagicMock()
    message.tool_calls = None
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _make_stub_client(tool_name: str, args: dict[str, Any], narrative: str) -> MagicMock:
    """Create a stub LLM client that returns a fixed plan then a narrative."""
    plan_resp = _make_planner_response(tool_name, args)
    narrative_resp = _make_narrative_response(narrative)
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[plan_resp, narrative_resp])
    return client


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


async def test_get_last_workout_returns_workout_card(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "get_last_workout",
        {"activity_type": "Running"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Show my last run")

    assert response.template_id == "workout_card"
    assert "activity_type" in response.data
    assert response.data["activity_type"] == "Running"
    assert response.data["duration_minutes"] == pytest.approx(45.5)
    assert response.narrative == "Test narrative."


async def test_planner_receives_local_coverage_instead_of_computer_date(
    db: duckdb.DuckDBPyConnection,
) -> None:
    """Relative language must be anchored to the health export's latest day."""
    client = _make_stub_client(
        "get_last_workout",
        {"activity_type": "Running"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]

    await orchestrator.answer("Show my last run")

    planner_messages = client.chat.completions.create.await_args_list[0].kwargs["messages"]
    planner_prompt = planner_messages[0]["content"]
    assert "Treat 2026-06-10 as today" in planner_prompt
    assert "Available workout types:" in planner_prompt
    assert "Running" in planner_prompt
    assert "Traditional Strength Training" in planner_prompt


async def test_get_top_workouts_returns_ranked_list(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "\tget_top_workouts",
        {"activity_type": "Running", "metric": "distance", "n": 5},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Top running workouts by distance")

    assert response.template_id == "ranked_list"
    assert "rows" in response.data
    assert len(response.data["rows"]) == 1
    assert response.data["rows"][0]["rank"] == 1


async def test_invalid_planner_output_uses_local_fallback_plan(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "not-a-real-tool",
        {"activity_type": "Running"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Show my last run")

    assert response.template_id == "workout_card"
    assert response.narrative == "Here is your most recent Running."


async def test_get_trend_returns_trend_chart(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "get_trend",
        {
            "metric_id": "HKQuantityTypeIdentifierRestingHeartRate",
            "granularity": "week",
            "start_date": "2026-06-01",
            "end_date": "2026-06-10",
        },
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Show resting HR trend")

    assert response.template_id == "trend_chart"
    assert "series" in response.data
    assert len(response.data["series"]) == 2


async def test_get_period_summary(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "get_period_summary",
        {"start_date": "2026-06-01", "end_date": "2026-06-10"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Summarise my training this month")

    assert response.template_id == "period_summary"
    assert "metrics" in response.data
    assert response.data["metrics"][0]["label"] == "Workouts"


async def test_get_comparison(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "get_comparison",
        {
            "this_start": "2026-06-06",
            "this_end": "2026-06-10",
            "last_start": "2026-06-01",
            "last_end": "2026-06-05",
            "this_label": "Jun 6-10",
            "last_label": "Jun 1-5",
        },
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Compare this week to last week")

    assert response.template_id == "comparison"
    assert "metrics" in response.data
    sessions_metric = next(m for m in response.data["metrics"] if m["label"] == "Sessions")
    assert sessions_metric["this_value"] == pytest.approx(2)
    assert sessions_metric["last_value"] == pytest.approx(1)


async def test_fallback_tool(
    db: duckdb.DuckDBPyConnection,
) -> None:
    client = _make_stub_client(
        "get_fallback_answer",
        {"text": "I don't know"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("What is the meaning of life?")

    assert response.template_id == "fallback"
    assert "question" in response.data


async def test_no_matching_workout_falls_back(
    db: duckdb.DuckDBPyConnection,
) -> None:
    # Swimming does not exist in the fixture → returns None → fallback
    client = _make_stub_client(
        "get_last_workout",
        {"activity_type": "Swimming"},
        "Test narrative.",
    )
    orchestrator = ChatOrchestrator(client=client, conn=db)  # type: ignore[arg-type]
    response = await orchestrator.answer("Show my last swim")

    assert response.template_id == "fallback"


# ---------------------------------------------------------------------------
# FastAPI endpoint test
# ---------------------------------------------------------------------------


async def test_chat_endpoint_integration(
    db: duckdb.DuckDBPyConnection,
) -> None:
    """Test the /api/chat endpoint with a stubbed LLM and a real in-memory DB."""
    stub_client = _make_stub_client(
        "get_last_workout",
        {"activity_type": "Running"},
        "You ran 45 minutes on June 5.",
    )

    app = create_app()

    # Override the DB dependency with the seeded in-memory DB
    from app.api.chat import _get_conn

    app.dependency_overrides[_get_conn] = lambda: (yield db)

    # Patch make_client so the router uses our stub
    import app.api.chat as chat_module

    original_make_client = chat_module.make_client
    chat_module.make_client = lambda: stub_client  # type: ignore[assignment]

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/chat", json={"question": "show my last run"})
    finally:
        chat_module.make_client = original_make_client  # type: ignore[assignment]
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "template_id" in body
    assert "data" in body
    assert "narrative" in body
    assert body["template_id"] == "workout_card"
