"""Concurrency integration test (T-01): parallel chat + dashboard.

The dashboard fires its panel set concurrently (sync handlers in the FastAPI
threadpool) while chat requests run on the event loop, all sharing one SQLite
app-state store and one DuckDB file. This is exactly the load that produced
``database is locked`` failures before WAL + busy_timeout (A-09). Every request
opens its own connection (read-only DuckDB per thread, one SQLite file), so the
test exercises real production connection handling rather than a shared handle.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest

from app.api.chat import _get_gateway
from app.ingest.coordinator import ingest_v2 as ingest
from app.llm.provider_gateway import ProviderGateway
from app.main import app
from app.state.diagnostics import DiagnosticsRepository

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"

# The full dashboard panel set, hit exactly as the SPA does.
PANEL_PATHS = [
    "/api/dashboard/summary",
    "/api/dashboard/workouts",
    "/api/dashboard/steps",
    "/api/dashboard/heart",
    "/api/dashboard/sleep",
    "/api/dashboard/sleep/stages",
    "/api/dashboard/capabilities",
]

# Both questions are resolved by the deterministic planner, so the chat path
# must answer them without ever touching the (stub) provider.
CHAT_QUESTIONS = ("Show my last run", "Top running workouts by distance")


@pytest.fixture
def db_file(tmp_path) -> Path:
    """A real on-disk DuckDB seeded from the synthetic fixture."""
    path = tmp_path / "fixture.duckdb"
    conn = duckdb.connect(str(path))
    ingest(str(FIXTURE), conn)
    conn.close()
    return path


def _local_only_client() -> MagicMock:
    """A stub client that fails loudly if a remote call is ever attempted."""
    client = MagicMock()

    async def _unexpected(*_args, **_kwargs) -> None:
        raise AssertionError("chat unexpectedly used the remote provider")

    client.chat.completions.create = AsyncMock(side_effect=_unexpected)
    return client


@pytest.mark.asyncio
async def test_parallel_chat_and_dashboard_shared_sqlite_no_lock(
    db_file: Path, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Concurrent panel + chat traffic completes with no lock errors and valid answers."""
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("TTI_DB_PATH", str(db_file))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    # Hermetic lifespan: autostart is covered in test_litert_lifecycle.py.
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "0")

    async def run_dashboard() -> list[int]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = await asyncio.gather(*(client.get(path) for path in PANEL_PATHS))
            return [response.status_code for response in statuses]

    async def run_chat() -> list[str]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = [
                await client.post("/api/chat", json={"question": question})
                for question in CHAT_QUESTIONS
            ]
            assert [response.status_code for response in responses] == [200, 200]
            return [response.json()["template_id"] for response in responses]

    # Only the optional provider is stubbed; every other dependency - the
    # lifespan-owned repositories, the request-scoped DuckDB connections, the
    # orchestrator and its tool dispatch - is exercised through the real HTTP path.
    gateway = ProviderGateway(_local_only_client(), provider="local", mode="local_only")
    app.dependency_overrides[_get_gateway] = lambda: gateway
    try:
        # Run the real lifespan first: in production it migrates both stores once
        # at startup before any request is served, which is what makes the
        # shared-store writes below safe to parallelize.
        async with app.router.lifespan_context(app):
            panels, chat_a, chat_b = await asyncio.gather(run_dashboard(), run_chat(), run_chat())
    finally:
        app.dependency_overrides.pop(_get_gateway, None)

    # Every panel answered; no 500s from locked SQLite or torn connections.
    assert panels == [200] * len(PANEL_PATHS)
    # Deterministic local chat is stable under contention.
    assert chat_a == chat_b
    assert set(chat_a) == {"workout_card", "ranked_list"}

    # The concurrent writes actually landed in the shared store, proving the
    # panel + chat writers interleaved without raising. Chat answers record a
    # per-tool ``query`` event; the API layer adds the ``chat`` event.
    repo = DiagnosticsRepository()
    assert repo.count("panel") >= len(PANEL_PATHS)
    assert repo.count("query") >= 2
    assert repo.count("chat") >= 2
