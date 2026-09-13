"""Local Apple Health import jobs exposed to the web application.

The browser uploads the export to a temporary file owned by the backend.  The
existing CLI importer is then run in an isolated subprocess so the FastAPI
event loop stays responsive and the same staging/activation safety checks are
used for both CLI and in-app imports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
IMPORT_TIMEOUT_SECONDS = float(os.environ.get("TTI_IMPORT_TIMEOUT_SECONDS", str(60 * 60)))
MAX_RETAINED_JOBS = 100
_IMPORT_PROCESSES: dict[str, subprocess.Popen[str]] = {}
# Upload paths whose import was cancelled before its subprocess was registered.
# The registration path checks this set so a cancellation cannot race the Popen
# call and leave an orphan importer running.
_CANCELLED_IMPORTS: set[str] = set()
_IMPORT_PROCESS_LOCK = threading.Lock()

_logger = logging.getLogger(__name__)


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
    cancelled: bool = False

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
        self._tasks_by_job: dict[str, asyncio.Task[None]] = {}
        self._uploads_by_job: dict[str, Path] = {}
        # Guarded by _lock: cancel() runs on a worker thread while _run() runs
        # on the event loop.
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

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
        if len(self.jobs) > MAX_RETAINED_JOBS:
            finished = sorted(
                (item for item in self.jobs.values() if item.state in {"succeeded", "failed"}),
                key=lambda item: item.created_at,
            )
            for stale in finished[: max(0, len(self.jobs) - MAX_RETAINED_JOBS)]:
                self.jobs.pop(stale.id, None)
        self._active_job_id = job.id
        self._uploads_by_job[job.id] = upload_path
        self._loop = asyncio.get_running_loop()
        task = asyncio.create_task(self._run(job, upload_path))
        self._tasks.add(task)
        self._tasks_by_job[job.id] = task
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(lambda _task, job_id=job.id: self._tasks_by_job.pop(job_id, None))
        return job.public()

    async def _run(self, job: _ImportJob, upload_path: Path) -> None:
        """Execute the existing importer off the event loop."""
        with self._lock:
            job.state = "running"
            job.progress = 10
            job.started_at = datetime.now(UTC).isoformat()
        try:
            report = await asyncio.to_thread(_run_import, upload_path)
        except Exception:
            with self._lock:
                # A cancellation owns the terminal state; never overwrite it.
                if not job.cancelled:
                    # The importer preserves the last active database on
                    # failure. Keep the browser-facing error stable and never
                    # expose subprocess text.
                    job.state = "failed"
                    job.error = "The import failed; your previous dataset was kept."
        else:
            with self._lock:
                if not job.cancelled:
                    job.report = report
                    job.state = "succeeded"
        finally:
            with self._lock:
                job.progress = 100
                job.completed_at = datetime.now(UTC).isoformat()
                # Only release the slot this job owns: a cancelled job may
                # already have been replaced by a newer import.
                if self._active_job_id == job.id:
                    self._active_job_id = None
                self._uploads_by_job.pop(job.id, None)
            upload_path.unlink(missing_ok=True)

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued/running job and release the active slot."""
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None or job.state not in {"queued", "running"}:
                return False
            job.cancelled = True
            job.state = "failed"
            job.progress = 100
            job.error = "The import was cancelled."
            job.completed_at = datetime.now(UTC).isoformat()
            task = self._tasks_by_job.get(job_id)
            upload_path = self._uploads_by_job.pop(job_id, None)
            if self._active_job_id == job_id:
                self._active_job_id = None
        # Signal the process group first so an in-flight subprocess stops even
        # if the waiting worker has not yet been cancelled.
        if upload_path is not None:
            _terminate_import_process(upload_path)
            # The worker may never run (cancelled before it started); remove the
            # upload here so a cancellation can never leave it behind.
            upload_path.unlink(missing_ok=True)
        if task is not None:
            self._cancel_task(task)
        return True

    def _cancel_task(self, task: asyncio.Task[None]) -> None:
        """Cancel a task on its own loop; Task.cancel is not thread-safe."""
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
                return
            except RuntimeError:
                _logger.debug("Import loop was closed before cancellation")
        task.cancel()


def _run_import(upload_path: Path) -> dict[str, object]:
    """Run the canonical V2 CLI importer and parse its safe JSON report."""
    backend_root = Path(__file__).resolve().parents[2]
    command = [sys.executable, "-m", "app.ingest.run", "--report-json", str(upload_path)]
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=backend_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    process_key = str(upload_path)
    try:
        with _IMPORT_PROCESS_LOCK:
            cancelled_before_registration = process_key in _CANCELLED_IMPORTS
            _IMPORT_PROCESSES[process_key] = process
        if cancelled_before_registration:
            # A cancellation arrived between job start and Popen registration.
            _signal_process_group(process, signal.SIGKILL)
            process.communicate()
            raise RuntimeError("import subprocess cancelled")
        try:
            stdout, _stderr = process.communicate(timeout=IMPORT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            # Kill the whole session: the importer spawns its own workers, and
            # killing only the direct child would leave them running.
            _signal_process_group(process, signal.SIGKILL)
            process.communicate()
            raise RuntimeError("import subprocess timed out") from exc
    finally:
        with _IMPORT_PROCESS_LOCK:
            _IMPORT_PROCESSES.pop(process_key, None)
            _CANCELLED_IMPORTS.discard(process_key)
    if process.returncode != 0:
        raise RuntimeError("import subprocess failed")

    for line in reversed(stdout.splitlines()):
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


def _terminate_import_process(upload_path: Path) -> None:
    """Terminate the subprocess group associated with an upload, if running.

    The caller records the cancellation first, so a process that registers
    after this returns is killed by the registration path instead.
    """
    process_key = str(upload_path)
    with _IMPORT_PROCESS_LOCK:
        _CANCELLED_IMPORTS.add(process_key)
        process = _IMPORT_PROCESSES.get(process_key)
    if process is None or process.poll() is not None:
        return
    _signal_process_group(process, signal.SIGTERM)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.05)
    _signal_process_group(process, signal.SIGKILL)


def _signal_process_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    """Signal a process group, falling back to the process on platforms without it."""
    try:
        os.killpg(process.pid, sig)
    except (AttributeError, OSError):
        if sig == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()


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


@router.delete("/{job_id}", response_model=ImportJob)
async def cancel_import(job_id: str) -> ImportJob:
    """Cancel a queued or running import job."""
    if not await asyncio.to_thread(import_jobs.cancel, job_id):
        raise HTTPException(status_code=409, detail="Import job is not cancellable")
    job = import_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


import_jobs = ImportJobManager()
