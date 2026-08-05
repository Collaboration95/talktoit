"""Integration tests for the diagnostics API and chat/panel instrumentation.

The app-state store is isolated per test via TTI_APP_STATE_PATH so recorded
events never touch a real local database.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.state.diagnostics import DiagnosticsRepository


async def test_diagnostics_summary_and_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    DiagnosticsRepository().record(
        "panel",
        "panel:steps",
        status="empty",
        duration_ms=4.0,
        meta={"panel_name": "steps", "state": "empty"},
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        summary = await client.get("/api/diagnostics")
        assert summary.status_code == 200
        body = summary.json()
        assert body["total_events"] >= 1
        assert "by_category" in body and "cache" in body
        assert body["by_category"]["panel"]["count"] >= 1

        events = await client.get("/api/diagnostics/events")
        assert events.status_code == 200
        assert events.json()["count"] >= 1
        assert events.json()["events"][0]["category"] == "panel"

        only_chat = await client.get("/api/diagnostics/events?category=chat")
        assert only_chat.status_code == 200
        assert all(event["category"] == "chat" for event in only_chat.json()["events"])


async def test_diagnostics_clear_is_independent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    DiagnosticsRepository().record("app", "startup", meta={"app_version": "0.1.0"})
    DiagnosticsRepository().record(
        "panel", "panel:steps", status="empty", meta={"panel_name": "steps", "state": "empty"}
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        cleared = await client.delete("/api/diagnostics")
        assert cleared.status_code == 200
        assert cleared.json()["cleared"] == 2
        assert (await client.get("/api/diagnostics")).json()["total_events"] == 0


async def test_diagnostics_export_requires_confirmation_and_is_redacted(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    DiagnosticsRepository().record(
        "chat", "run", meta={"plan_mode": "local", "cache_outcome": "local"}
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        refused = await client.post("/api/diagnostics/export", json={"confirmed": False})
        assert refused.status_code == 422

        exported = await client.post("/api/diagnostics/export", json={"confirmed": True})
        assert exported.status_code == 200
        body = exported.json()
        assert body["redacted"] is True
        payload = str(body).casefold()
        for token in ("question", "select ", "from workouts", "conversation_id", ".xml"):
            assert token not in payload


async def test_unknown_diagnostics_category_is_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/diagnostics/events?category=secrets")
        assert response.status_code == 422


async def test_chat_and_planner_events_recorded_on_local_answer(monkeypatch, tmp_path) -> None:
    """A deterministic local chat answer records chat, planner, and query events."""
    from pathlib import Path
    from unittest.mock import MagicMock

    import duckdb

    from app.api.chat import _get_conn, _get_gateway
    from app.ingest.parser import ingest
    from app.main import create_app

    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
    db = duckdb.connect(":memory:")
    ingest(str(fixture), db)

    stub = MagicMock()
    from app.llm.provider_gateway import ProviderGateway

    app = create_app()
    app.dependency_overrides[_get_conn] = lambda: (yield db)
    app.dependency_overrides[_get_gateway] = lambda: ProviderGateway(
        stub, mode="remote_planning_and_narration"
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/chat", json={"question": "show my last run"})
            assert response.status_code == 200
            assert response.json()["metadata"]["provenance"] == "deterministic_local"
    finally:
        app.dependency_overrides.clear()

    repo = DiagnosticsRepository()
    chats = repo.recent(category="chat")
    planners = repo.recent(category="planner")
    queries = repo.recent(category="query")
    assert any(event.name == "chat_request" for event in chats)
    assert any(event.meta.get("plan_mode") == "local" for event in chats)
    assert any(event.meta.get("mode") == "local" for event in planners)
    assert any(event.meta.get("query_name") == "get_last_workout" for event in queries)
