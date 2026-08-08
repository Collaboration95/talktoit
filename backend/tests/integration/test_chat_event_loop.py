"""Regression (issue #15): chat DB work must not run on the async event loop.

The chat endpoint used to run DuckDB tool calls, SQLite app-state writes, and
diagnostics on the ``async def`` handler's event loop, so one slow aggregate
stalled every other request (health checks, dashboard, other chats). This test
drives ``POST /api/chat`` through the real ASGI app and blocks inside the tool
dispatch with threading events — no wall-clock sleeps — then proves the tool ran
on a worker thread and that the loop kept serving another request while the
chat was still processing. After release, the chat completes normally.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingest.parser import ingest
from app.llm import orchestrator as orchestrator_module
from app.main import app

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.fixture
def db_file(tmp_path) -> Path:
    """A real on-disk DuckDB seeded from the synthetic fixture."""
    path = tmp_path / "fixture.duckdb"
    conn = duckdb.connect(str(path))
    ingest(str(FIXTURE), conn)
    conn.close()
    return path


@pytest.mark.asyncio
async def test_chat_offloads_db_work_and_keeps_the_event_loop_live(
    db_file: Path, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A blocked chat tool must not stop the loop; its work runs on a thread."""
    monkeypatch.setenv("TTI_DB_PATH", str(db_file))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_PROVIDER_MODE", "local_only")

    loop_thread_id = threading.get_ident()
    real_dispatch = orchestrator_module.dispatch_tool
    entered = threading.Event()
    release = threading.Event()
    worker_thread_ids: list[int] = []

    def _blocking_dispatch(
        tool_name: str,
        args: dict,
        conn: duckdb.DuckDBPyConnection,
        question: str,
    ) -> tuple[str, dict[str, object]]:
        worker_thread_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=10)
        return real_dispatch(tool_name, args, conn, question)

    monkeypatch.setattr(orchestrator_module, "dispatch_tool", _blocking_dispatch)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            chat_task = asyncio.create_task(
                client.post("/api/chat", json={"question": "Show my last run"})
            )
            # Wait (off the loop) until the chat request is inside the DB tool.
            assert await asyncio.to_thread(entered.wait, 10), "chat tool work never ran"
            # The tool dispatch executed on a worker thread, never the loop.
            assert worker_thread_ids and worker_thread_ids[0] != loop_thread_id
            # While that chat request is still blocked in a thread, the event
            # loop keeps serving other requests — the actual regression check.
            health = await asyncio.wait_for(client.get("/api/health"), timeout=5)
            assert health.status_code == 200
            release.set()
            response = await asyncio.wait_for(chat_task, timeout=30)

    assert response.status_code == 200
    body = response.json()
    assert body["template_id"] == "workout_card"
    assert body["metadata"]["provenance"] == "deterministic_local"
