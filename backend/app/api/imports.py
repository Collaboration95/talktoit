"""Local Apple Health import jobs exposed to the web application.

The browser uploads the export to a temporary file owned by the backend.  The
existing CLI importer is then run in an isolated subprocess so the FastAPI
event loop stays responsive and the same staging/activation safety checks are
used for both CLI and in-app imports.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.db.connection import resolve_db_path

router = APIRouter(prefix="/api/imports", tags=["imports"])

ImportState = Literal["queued", "running", "succeeded", "failed"]
MAX_IMPORT_BYTES = int(os.environ.get("TTI_IMPORT_MAX_BYTES", str(2 * 1024**3)))


class ImportJob(BaseModel):
    """Safe progress envelope for one local import job."""

    id: str
    filename: str
    state: ImportState
    progress: int = Field(ge=0, le=100)
    report: dict[str, object] | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class _ImportJob:
    """Mutable in-process job state; only safe fields leave this module."""

    id: str
    filename: str
    state: ImportState
    progress: int
    created_at: str
    report: dict[str, object] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def public(self) -> ImportJob:
        """Return the API representation without local paths or subprocess output."""
        return ImportJob(
            id=self.id,
            filename=self.filename,
            state=self.state,
            progress=self.progress,
            report=self.report,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


class ImportJobManager:
    """Keep a bounded set of local import jobs and serialize activation."""

    def __init__(self) -> None:
        """Create an empty process-local job store."""
        self.jobs: dict[str, _ImportJob] = {}
        self._active_job_id: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def list(self) -> list[ImportJob]:
        """Return recent jobs, newest first."""
        jobs = sorted(self.jobs.values(), key=lambda job: job.created_at, reverse=True)
        return [job.public() for job in jobs[:20]]

    def get(self, job_id: str) -> ImportJob | None:
        """Return one job when it exists."""
        job = self.jobs.get(job_id)
        return job.public() if job else None

    def start(self, filename: str, upload_path: Path) -> ImportJob:
        """Queue one upload and start its background import task."""
        if self._active_job_id is not None:
            active = self.jobs.get(self._active_job_id)
            if active and active.state in {"queued", "running"}:
                upload_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another health import is already running.",
                )

        now = datetime.now(UTC).isoformat()
        job = _ImportJob(
            id=uuid.uuid4().hex,
            filename=filename,
            state="queued",
            progress=0,
            created_at=now,
        )
        self.jobs[job.id] = job
        self._active_job_id = job.id
        task = asyncio.create_task(self._run(job, upload_path))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job.public()

    async def _run(self, job: _ImportJob, upload_path: Path) -> None:
        """Execute the existing importer off the event loop."""
        job.state = "running"
        job.progress = 10
        job.started_at = datetime.now(UTC).isoformat()
        try:
            job.report = await asyncio.to_thread(_run_import, upload_path)
            job.state = "succeeded"
            job.progress = 100
        except Exception:
            # The importer preserves the last active database on failure. Keep
            # the browser-facing error stable and never expose subprocess text.
            job.state = "failed"
            job.progress = 100
            job.error = "The import failed; your previous dataset was kept."
        finally:
            job.completed_at = datetime.now(UTC).isoformat()
            self._active_job_id = None
            upload_path.unlink(missing_ok=True)


def _run_import(upload_path: Path) -> dict[str, object]:
    """Run the canonical V2 CLI importer and parse its safe JSON report."""
    backend_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.ingest.run", "--report-json", str(upload_path)],
        cwd=backend_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("import subprocess failed")

    for line in reversed(completed.stdout.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            report = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(report, dict):
            return report
    raise RuntimeError("import report was not produced")


async def _write_upload(request: Request, filename: str) -> tuple[Path, int]:
    """Stream one XML request body to a temporary local file."""
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=422, detail="Choose an Apple Health .xml export.")

    directory = resolve_db_path().parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="tti-upload-", suffix=".xml", dir=directory)
    path = Path(name)
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMPORT_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="The export is larger than the configured import limit.",
                    )
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=422, detail="The export file is empty.")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, total


@router.post("", response_model=ImportJob, status_code=status.HTTP_202_ACCEPTED)
async def create_import(
    request: Request,
    filename: str = Query(default="export.xml", min_length=1, max_length=255),
) -> ImportJob:
    """Accept an XML export and queue a safe local import."""
    safe_filename = Path(filename).name
    upload_path, _size = await _write_upload(request, safe_filename)
    return import_jobs.start(safe_filename, upload_path)


@router.get("", response_model=list[ImportJob])
async def list_imports() -> list[ImportJob]:
    """Return recent import jobs."""
    return import_jobs.list()


@router.get("/{job_id}", response_model=ImportJob)
async def get_import(job_id: str) -> ImportJob:
    """Return one import job."""
    job = import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


import_jobs = ImportJobManager()
