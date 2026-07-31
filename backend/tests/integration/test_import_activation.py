"""API contract for safe active-import status."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.state.app_state import AppStateRepository


@pytest.mark.asyncio
async def test_status_reports_no_active_import(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")
    assert response.json() == {"readiness": "no_active_import", "dataset": None}


@pytest.mark.asyncio
async def test_status_exposes_safe_active_manifest(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.sqlite"
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(state_path))
    AppStateRepository().activate(
        source_bytes=b"fixture",
        source_size_bytes=7,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2024-01-01",
        coverage_end="2024-01-02",
        counts={"workouts": 1},
        warnings=("sample warning",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        body = (await client.get("/api/status")).json()
    assert body["readiness"] == "ready"
    assert body["dataset"]["coverage_end"] == "2024-01-02"
    assert "source_path" not in body["dataset"]
