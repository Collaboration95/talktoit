"""Conversation API contracts use only local app-state data."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.state.app_state import AppStateRepository


@pytest.mark.asyncio
async def test_conversation_lifecycle_through_api(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(state_path))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        created = await client.post("/api/conversations", json={"title": "Runs"})
        assert created.status_code == 200
        conversation_id = created.json()["id"]
        assert (await client.get("/api/conversations")).json()[0]["title"] == "Runs"

        repository = AppStateRepository()
        repository.add_completed_turn(
            conversation_id,
            "Show my last run",
            '{"template_id":"workout_card"}',
            "default",
            "deterministic_local",
        )
        turns = await client.get(f"/api/conversations/{conversation_id}/turns")
        assert turns.status_code == 200
        assert turns.json()[0]["question"] == "Show my last run"

        assert (
            await client.patch(f"/api/conversations/{conversation_id}", json={"title": "Running"})
        ).json() == {"ok": True}
        assert (await client.delete(f"/api/conversations/{conversation_id}")).json() == {"ok": True}
        assert (await client.get("/api/conversations")).json() == []


@pytest.mark.asyncio
async def test_scoped_turn_get_and_cancel_through_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        first = (await client.post("/api/conversations", json={"title": "First"})).json()["id"]
        second = (await client.post("/api/conversations", json={"title": "Second"})).json()["id"]
        turn_id = AppStateRepository().create_pending_turn(first, "Slow question", "default")

        turn = await client.get(f"/api/conversations/{first}/turns/{turn_id}")
        assert turn.status_code == 200
        assert turn.json()["state"] == "pending"
        assert (
            await client.post(f"/api/conversations/{second}/turns/{turn_id}/cancel")
        ).status_code == 404
        cancelled = await client.post(f"/api/conversations/{first}/turns/{turn_id}/cancel")
        assert cancelled.json() == {"ok": True}
        fetched = await client.get(f"/api/conversations/{first}/turns/{turn_id}")
        assert fetched.json()["state"] == "cancelled"
        assert (
            await client.post(f"/api/conversations/{first}/turns/{turn_id}/cancel")
        ).status_code == 409


def test_followup_parent_cannot_cross_conversation_scope(monkeypatch, tmp_path) -> None:
    """Follow-up resolution must not read a parent turn from another conversation."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    first = repo.create_conversation("First", "ds_fixture")
    second = repo.create_conversation("Second", "ds_fixture")
    parent_id = repo.add_completed_turn(
        first,
        "Show my training summary",
        '{"template_id":"period_summary"}',
        "default",
        "deterministic_local",
        canonical_plan={
            "tool_name": "get_period_summary",
            "arguments": {"start_date": "2024-01-01", "end_date": "2024-01-07"},
        },
    )

    assert repo.get_conversation_turn(second, parent_id) is None
