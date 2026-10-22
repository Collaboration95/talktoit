"""API contract for safe active-import status."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


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
    from tests.integration.test_dataset_crash_recovery import _child, _export

    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    export = _export(tmp_path, "status-root", 42, 1)
    export.write_text(export.read_text().replace("2024-01-01", "2024-01-02"))
    _child(tmp_path, "import", export)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        body = (await client.get("/api/status")).json()
    assert body["readiness"] == "ready"
    assert body["dataset"]["coverage_end"] == "2024-01-02"
    assert "source_path" not in body["dataset"]
