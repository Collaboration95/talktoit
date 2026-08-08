"""Chat cache revalidation: stale-valid hits; fresh datasets and fresh mode refetch.

Exercises the real ``/api/chat`` endpoint against an in-memory DuckDB seeded
from the synthetic fixture. The app-state is isolated per request via
``TTI_APP_STATE_PATH`` so cache entries never leak across tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingest.parser import ingest
from app.main import create_app
from app.state.app_state import AppStateRepository

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


def _activate(repo: AppStateRepository, *, records: int, coverage_end: str) -> str:
    """Activate a fresh dataset manifest (a new ``ds_*`` id each call)."""
    version = repo.activate(
        source_bytes=b"",
        source_size_bytes=records * 1024,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-01-01",
        coverage_end=coverage_end,
        counts={"records": records},
        content_hash_prefix=f"{records:x}0000",
    )
    assert version is not None
    return version.id


async def _run(
    client: AsyncClient, question: str, *, cache_mode: str = "default"
) -> dict[str, Any]:
    """POST one chat request and return the parsed response envelope."""
    response = await client.post(
        "/api/chat",
        json={"question": question, "cache_mode": cache_mode},
    )
    assert response.status_code == 200
    return response.json()


def _app_with_db(db: duckdb.DuckDBPyConnection):
    """Build the app with the seeded DuckDB and a stub remote provider.

    The stub is never awaited: the questions in these tests resolve through the
    deterministic local planner, and the cache assertions only need the
    endpoint's exact/canonical cache wiring.
    """
    from unittest.mock import MagicMock

    from app.api.chat import _get_conn, _get_gateway
    from app.llm.provider_gateway import ProviderGateway

    app = create_app()
    app.dependency_overrides[_get_conn] = lambda: (yield db)
    app.dependency_overrides[_get_gateway] = lambda: ProviderGateway(
        MagicMock(), mode="remote_planning_and_narration"
    )
    return app


@pytest.mark.asyncio
async def test_reingest_invalidates_cached_answers_and_refetches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """A warm cache serves the stale answer until re-ingest forces a refetch."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    old_dataset_id = _activate(repo, records=100, coverage_end="2026-06-30")

    db = duckdb.connect(":memory:")
    ingest(str(FIXTURE), db)

    app = _app_with_db(db)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await _run(client, "show my last run")
            second = await _run(client, "show my last run")
            assert first["metadata"]["provenance"] == "deterministic_local"
            assert second["metadata"]["provenance"] == "cached"
            assert second["data"] == first["data"]

            # Re-ingest: a freshly activated dataset (new coverage) must NOT be
            # served the stale cached envelope — the endpoint refetches locally.
            assert _activate(repo, records=104, coverage_end="2026-07-31") != old_dataset_id
            revalidated = await _run(client, "show my last run")
            assert revalidated["metadata"]["provenance"] == "deterministic_local"
            assert revalidated["data"] == first["data"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cache_mode_fresh_always_refetches_even_with_warm_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """``cache_mode="fresh"`` bypasses the exact cache and refetches locally."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    _activate(repo, records=100, coverage_end="2026-06-01")

    db = duckdb.connect(":memory:")
    ingest(str(FIXTURE), db)

    app = _app_with_db(db)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await _run(client, "show my last run")
            cached = await _run(client, "show my last run")
            assert cached["metadata"]["provenance"] == "cached"

            fresh = await _run(client, "show my last run", cache_mode="fresh")
            assert fresh["metadata"]["provenance"] == "deterministic_local"

            # A later default call hits the warm cache again — and the fresh
            # call must not have replaced the cached envelope.
            afterwards = await _run(client, "show my last run")
            assert afterwards["metadata"]["provenance"] == "cached"
            assert afterwards["data"] == first["data"]
    finally:
        app.dependency_overrides.clear()
