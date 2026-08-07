"""P6-03 chat flow: provably-identical prior intents auto-serve; weaker stay misses."""

from __future__ import annotations

import duckdb
from httpx import ASGITransport, AsyncClient

from app.db.migrate import migrate
from app.db.schema import SQL_CREATE_TABLES
from app.main import create_app
from app.state.app_state import AppStateRepository

PRIOR_RESPONSE = (
    '{"template_id":"fallback","data":{"question":"Show my last run",'
    '"table":null,"text":"Here is your most recent workout."},'
    '"narrative":"Here is your most recent workout.",'
    '"metadata":{"provenance":"deterministic_local","api_version":"v1"}}'
)

LAST_RUN_PLAN = {
    "tool_name": "get_last_workout",
    "arguments": {"activity_type": "Running"},
}


def _seed(monkeypatch, tmp_path) -> AppStateRepository:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    db_path = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(db_path))


def _seed(monkeypatch, tmp_path) -> AppStateRepository:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    db_path = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(db_path))
    conn = duckdb.connect(str(db_path))
    conn.execute(SQL_CREATE_TABLES)
    # A single record gives local coverage so the planner has a reference date.
    conn.execute(
        """
        INSERT INTO records (id, type, source_name, start_date, end_date, value, unit)
        VALUES (1, 'HKQuantityTypeIdentifierStepCount', 'Phone',
                TIMESTAMP '2026-08-05 08:00:00', TIMESTAMP '2026-08-05 08:10:00', 100, 'count')
        """
    )
    conn.close()
    migrate(str(db_path))
    repo = AppStateRepository()
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
        PRIOR_RESPONSE,
        "default",
        "deterministic_local",
        canonical_plan=LAST_RUN_PLAN,
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
