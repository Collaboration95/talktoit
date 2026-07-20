"""Conversation API contracts use only local app-state data."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.state.app_state import AppStateRepository


def test_conversation_lifecycle_through_api(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(state_path))
    with TestClient(create_app()) as client:
        created = client.post("/api/conversations", json={"title": "Runs"})
        assert created.status_code == 200
        conversation_id = created.json()["id"]
        assert client.get("/api/conversations").json()[0]["title"] == "Runs"

        repository = AppStateRepository()
        repository.add_completed_turn(
            conversation_id,
            "Show my last run",
            '{"template_id":"workout_card"}',
            "default",
            "deterministic_local",
        )
        turns = client.get(f"/api/conversations/{conversation_id}/turns")
        assert turns.status_code == 200
        assert turns.json()[0]["question"] == "Show my last run"

        assert client.patch(
            f"/api/conversations/{conversation_id}", json={"title": "Running"}
        ).json() == {"ok": True}
        assert client.delete(f"/api/conversations/{conversation_id}").json() == {"ok": True}
        assert client.get("/api/conversations").json() == []


def test_scoped_turn_get_and_cancel_through_api(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    with TestClient(create_app()) as client:
        first = client.post("/api/conversations", json={"title": "First"}).json()["id"]
        second = client.post("/api/conversations", json={"title": "Second"}).json()["id"]
        turn_id = AppStateRepository().create_pending_turn(first, "Slow question", "default")

        turn = client.get(f"/api/conversations/{first}/turns/{turn_id}")
        assert turn.status_code == 200
        assert turn.json()["state"] == "pending"
        assert client.post(f"/api/conversations/{second}/turns/{turn_id}/cancel").status_code == 404
        cancelled = client.post(f"/api/conversations/{first}/turns/{turn_id}/cancel")
        assert cancelled.json() == {"ok": True}
        fetched = client.get(f"/api/conversations/{first}/turns/{turn_id}")
        assert fetched.json()["state"] == "cancelled"
        assert client.post(f"/api/conversations/{first}/turns/{turn_id}/cancel").status_code == 409
