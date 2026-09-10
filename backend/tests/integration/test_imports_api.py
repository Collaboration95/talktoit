"""Contract tests for the local in-app import manager."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import imports
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_import_jobs() -> None:
    """Keep the process-local job manager isolated between tests."""
    imports.import_jobs.jobs.clear()
    imports.import_jobs._active_job_id = None
    yield
    imports.import_jobs.jobs.clear()
    imports.import_jobs._active_job_id = None


@pytest.mark.asyncio
async def test_import_rejects_non_xml_upload(monkeypatch, tmp_path) -> None:
    """Only Apple Health XML exports can enter the import pipeline."""
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post("/api/imports?filename=health.zip", content=b"not an export")
    assert response.status_code == 422
    assert response.json()["detail"] == "Choose an Apple Health .xml export."


@pytest.mark.asyncio
async def test_import_job_reports_safe_completion(monkeypatch, tmp_path) -> None:
    """An uploaded export returns a pollable report without local paths."""
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))

    def fake_import(path):
        assert path.exists()
        return {
            "mode": "v2",
            "source_size_bytes": path.stat().st_size,
            "resolved_workers": 1,
            "dataset_version_id": "ds_test",
            "coverage_start": "2026-01-01",
            "coverage_end": "2026-01-02",
            "counts": {"records": 1},
            "timing_seconds": {"total_time_seconds": 0.01},
            "warnings": [],
        }

    monkeypatch.setattr(imports, "_run_import", fake_import)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        created = await client.post("/api/imports?filename=export.xml", content=b"<HealthData />")
        assert created.status_code == 202
        job_id = created.json()["id"]

        for _ in range(20):
            job = (await client.get(f"/api/imports/{job_id}")).json()
            if job["state"] in {"succeeded", "failed"}:
                break
            await asyncio.sleep(0.01)

    assert job["state"] == "succeeded"
    assert job["progress"] == 100
    assert job["report"]["dataset_version_id"] == "ds_test"
    assert "/" not in str(job["report"])
