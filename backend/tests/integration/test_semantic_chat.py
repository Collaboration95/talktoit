"""P6-03 chat flow: provably-identical prior intents auto-serve; weaker stay misses."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.llm.cache_keys import snapshot_plan
from app.main import create_app
from app.state.app_state import AppStateRepository

PRIOR_RESPONSE = (
    '{"template_id":"workout_card","data":{"activity_type":"Running",'
    '"date":"2026-08-05T00:00:00+00:00","duration_minutes":30,'
    '"avg_heart_rate":null,"max_heart_rate":null,"distance_meters":null,'
    '"distance_unit":"m","energy_burned_kj":null,"elevation_ascent_meters":null},'
    '"narrative":"Here is your most recent workout.",'
    '"metadata":{"provenance":"deterministic_local","api_version":"v1"}}'
)

LAST_RUN_PLAN = {
    "tool_name": "get_last_workout",
    "arguments": {"activity_type": "Running"},
}


def _seed(monkeypatch, tmp_path) -> AppStateRepository:
    from tests.integration.test_dataset_crash_recovery import _child, _export

    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    export = _export(tmp_path, "semantic-root", 100, 1)
    export.write_text(export.read_text().replace("2024-01-01", "2026-08-05"))
    _child(tmp_path, "import", export)
    repo = AppStateRepository()
    active = repo.get_active()
    assert active is not None
    conversation_id = repo.create_conversation("Runs", active.id)
    repo.add_completed_turn(
        conversation_id,
        "Show my last run",
        PRIOR_RESPONSE,
        "default",
        "deterministic_local",
        canonical_plan=snapshot_plan(LAST_RUN_PLAN),
    )
    return repo


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_differently_written_identical_intent_auto_serves(monkeypatch, tmp_path) -> None:
    _seed(monkeypatch, tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post("/api/chat", json={"question": "Show me my most recent run"})
        assert response.status_code == 200
        body = response.json()
        assert body["metadata"]["provenance"] == "semantic_cached"
        assert body["narrative"] == "Here is your most recent workout."


@pytest.mark.asyncio
async def test_last_long_run_does_not_reuse_plain_last_run(monkeypatch, tmp_path) -> None:
    _seed(monkeypatch, tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post("/api/chat", json={"question": "What was my last long run?"})
        assert response.status_code == 200
        # "Last long run" implies a minimum duration that the stored "last run"
        # intent does not, so the verifier refuses to auto-serve it.
        assert response.json()["metadata"]["provenance"] != "semantic_cached"
