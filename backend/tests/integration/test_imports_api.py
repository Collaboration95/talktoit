"""Contract tests for the local in-app import manager."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from pathlib import Path

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


@pytest.mark.asyncio
async def test_cancelled_import_releases_slot_and_removes_the_upload(monkeypatch, tmp_path) -> None:
    """A cancelled import stops the worker, clears the slot, and drops the upload."""
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    entered = threading.Event()
    release = threading.Event()
    seen: list[Path] = []

    def blocking_import(path: Path) -> dict[str, object]:
        seen.append(path)
        entered.set()
        assert release.wait(timeout=10)
        return {"mode": "v2", "counts": {}, "warnings": []}

    monkeypatch.setattr(imports, "_run_import", blocking_import)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        created = await client.post("/api/imports?filename=export.xml", content=b"<HealthData />")
        job_id = created.json()["id"]
        assert await asyncio.to_thread(entered.wait, 10), "import worker never started"
        upload_path = seen[0]
        assert upload_path.exists()

        cancelled = await client.delete(f"/api/imports/{job_id}")
        assert cancelled.status_code == 200
        body = cancelled.json()
        assert body["state"] == "failed"
        assert body["error"] == "The import was cancelled."
        # The upload is removed even though the worker is still blocked.
        assert not upload_path.exists()

        # The freed slot must accept the next import.
        next_job = await client.post("/api/imports?filename=export.xml", content=b"<HealthData />")
        assert next_job.status_code == 202
        release.set()


def test_cancellation_racing_registration_kills_the_importer(monkeypatch, tmp_path) -> None:
    """A cancel that lands before Popen registration still stops the process."""
    upload = tmp_path / "export.xml"
    upload.write_text("<HealthData/>")
    imports._CANCELLED_IMPORTS.add(str(upload))
    real_popen = subprocess.Popen
    started: list[subprocess.Popen[str]] = []

    def _fake_popen(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
        del command
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            **kwargs,  # type: ignore[arg-type]
        )
        started.append(process)
        return process

    monkeypatch.setattr(imports.subprocess, "Popen", _fake_popen)

    with pytest.raises(RuntimeError, match="cancelled"):
        imports._run_import(upload)

    assert started and started[0].returncode is not None
    assert str(upload) not in imports._CANCELLED_IMPORTS
