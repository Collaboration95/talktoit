"""Private import ownership records and conservative restart reconciliation.

A stable shared operation flock spans upload, subprocess handoff and workers.
Cleanup requires the exclusive lock plus matching store, lock, parent and child
inodes. Published generations are deliberately outside this module's authority.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import stat
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.dataset_lifecycle import DatasetLifecycle
from app.state.app_state import AppStateRepository
from app.state.cleanup_claims import authority_key, identity, remove_entry
from app.state.cleanup_claims import directory as claim_directory

_CURRENT: ContextVar[ImportOperation | None] = ContextVar("import_operation", default=None)
_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_RECORD = 1024 * 1024
_INTERRUPTED = "The import was interrupted. Choose your export to try again."


def _now() -> str:
    return datetime.now(UTC).isoformat()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Identity(_Strict):
    """A path's exact device/inode identity, never a PID or age heuristic."""

    device: int
    inode: int


class JobRecord(_Strict):
    """Only the existing public job envelope is persisted, without source paths."""

    id: str
    filename: str
    state: Literal["queued", "running", "succeeded", "failed"]
    progress: int = Field(ge=0, le=100)
    report: dict[str, object] | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        """Use an opaque operation id, never a path."""
        if not _ID.fullmatch(value):
            raise ValueError("Invalid job identity")
        return value

    @field_validator("filename")
    @classmethod
    def valid_filename(cls, value: str) -> str:
        """Persist only a display basename."""
        if not value or len(value) > 255 or "/" in value or "\\" in value:
            raise ValueError("Invalid display filename")
        return value

    @field_validator("error")
    @classmethod
    def safe_error(cls, value: str | None) -> str | None:
        """Reject arbitrary error/subprocess text from persisted state."""
        if value not in {
            None,
            _INTERRUPTED,
            "The import was cancelled.",
            "The import did not finish. Choose your export to try again.",
        }:
            raise ValueError("Invalid job error")
        return value

    @field_validator("report")
    @classmethod
    def safe_job_report(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        """Expose only allowlisted measured fields."""
        return safe_report(value) if value is not None else None


class Artifact(_Strict):
    """One allocated file or private run child beneath an exact parent inode."""

    kind: Literal["upload", "shards", "staging"]
    path: str
    identity: Identity
    parent: Identity


class _Record(_Strict):
    format_version: Literal[1] = 1
    operation_id: str
    store: Identity
    directory: Identity
    lock: Identity
    created_at: str
    closed: bool = False
    job: JobRecord | None = None
    generation_id: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)


def _identity(path: Path) -> Identity:
    current = path.lstat()
    if stat.S_ISLNK(current.st_mode) or path.resolve() != path:
        raise ValueError("Import ownership is ambiguous")
    return Identity(device=current.st_dev, inode=current.st_ino)


def _sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read(path: Path) -> _Record:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate ownership field")
            result[key] = value
        return result

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Invalid ownership record")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_RECORD + 1)
        if len(raw) > _MAX_RECORD:
            raise ValueError("Oversize ownership record")
        json.loads(raw, object_pairs_hook=unique)
        return _Record.model_validate_json(raw)
    finally:
        os.close(fd)


class ImportOperation:
    """An allocated operation holding a stable shared OS lock until close."""

    def __init__(self, lifecycle: DatasetLifecycle, operation_id: str, fd: int) -> None:
        """Use create/attach to validate before constructing a handle."""
        self.lifecycle = lifecycle
        self.id = operation_id
        self.directory = lifecycle.root / "imports" / operation_id
        self.record_path = self.directory / "record.json"
        self.lock_path = self.directory / "operation.lock"
        self.upload_path = self.directory / "upload.xml"
        self.fd = fd

    @classmethod
    def create(cls, lifecycle: DatasetLifecycle) -> ImportOperation:
        """Allocate and persist ownership before any upload bytes or handoff."""
        lifecycle.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _identity(lifecycle.root)
        store = lifecycle.root / "imports"
        store.mkdir(mode=0o700, exist_ok=True)
        store_identity = _identity(store)
        operation_id = uuid.uuid4().hex
        directory = store / operation_id
        directory.mkdir(mode=0o700)
        fd = os.open(directory / "operation.lock", os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            operation = cls(lifecycle, operation_id, fd)
            record = _Record(
                operation_id=operation_id,
                store=store_identity,
                directory=_identity(directory),
                lock=_identity(operation.lock_path),
                created_at=_now(),
            )
            operation.write_record(record)
            upload_fd = os.open(operation.upload_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(upload_fd)
            record.artifacts.append(operation._artifact("upload", operation.upload_path))
            operation.write_record(record)
            _sync(store)
            _sync(lifecycle.root)
            return operation
        except BaseException:
            os.close(fd)
            raise

    @classmethod
    def attach(cls, lifecycle: DatasetLifecycle, operation_id: str) -> ImportOperation:
        """Join live work; a late worker cannot restart a recovered operation."""
        if not _ID.fullmatch(operation_id):
            raise ValueError("Invalid import operation")
        directory = lifecycle.root / "imports" / operation_id
        _identity(directory)
        fd = os.open(directory / "operation.lock", os.O_RDWR | os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            operation = cls(lifecycle, operation_id, fd)
            record = operation.read_record()
            if record.closed:
                raise ValueError("Import operation is already complete")
            return operation
        except BaseException:
            os.close(fd)
            raise

    def read_record(self) -> _Record:
        """Read a strict record bound to this open stable lock inode."""
        record = _read(self.record_path)
        lock_stat = os.fstat(self.fd)
        if (
            record.operation_id != self.id
            or (record.job is not None and record.job.id != self.id)
            or record.store != _identity(self.directory.parent)
            or record.directory != _identity(self.directory)
            or record.lock != _identity(self.lock_path)
            or record.lock != Identity(device=lock_stat.st_dev, inode=lock_stat.st_ino)
            or not stat.S_ISREG(lock_stat.st_mode)
        ):
            raise ValueError("Import ownership changed")
        return record

    def write_record(self, record: _Record) -> None:
        """Atomically flush a validated private record and its parent."""
        temporary = self.directory / f"record.{uuid.uuid4().hex}.tmp"
        with temporary.open("xb") as handle:
            handle.write(record.model_dump_json().encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.record_path)
        _sync(self.directory)

    def _artifact(self, kind: Literal["upload", "shards", "staging"], path: Path) -> Artifact:
        return Artifact(
            kind=kind, path=str(path), identity=_identity(path), parent=_identity(path.parent)
        )

    def new_directory(self, kind: Literal["shards", "staging"], parent: Path) -> Path:
        """Allocate one recorded empty child; never adopt an existing caller path."""
        parent = parent.resolve()
        if kind == "staging" and parent != self.lifecycle.root / "staging":
            raise ValueError("Invalid staging root")
        if parent.is_relative_to(self.lifecycle.root) and parent != self.lifecycle.root / kind:
            raise ValueError("Invalid artifact root")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _identity(parent)
        path = parent / f"tti_{kind}_{uuid.uuid4().hex}"
        path.mkdir(mode=0o700)
        record = self.read_record()
        record.artifacts.append(self._artifact(kind, path))
        self.write_record(record)
        _sync(parent)
        return path

    def save_job(self, job: JobRecord) -> None:
        """Save safe progress before subprocess handoff and at observed transitions."""
        if job.id != self.id:
            raise ValueError("Import job ownership mismatch")
        record = self.read_record()
        record.job = job
        self.write_record(record)

    def set_generation(self, generation_id: str) -> None:
        """Associate intended activation before publication, for honest recovery."""
        if not re.fullmatch(r"ds_[0-9a-f]{32}", generation_id):
            raise ValueError("Invalid generation identity")
        record = self.read_record()
        record.generation_id = generation_id
        self.write_record(record)

    def close(self) -> None:
        """Release this owner's handle; never unlink the stable lock inode."""
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    @contextmanager
    def current(self) -> Generator[None, None, None]:
        """Pass ownership through the in-process coordinator without global state."""
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)


def current_operation() -> ImportOperation | None:
    """Return the caller's import context, if there is one."""
    return _CURRENT.get()


def _remove_artifact(artifact: Artifact, operation: ImportOperation) -> None:
    path = Path(artifact.path)
    root = operation.lifecycle.root
    if not path.is_absolute():
        return
    if artifact.kind != "upload" and not re.fullmatch(
        rf"tti_{artifact.kind}_[0-9a-f]{{32}}", path.name
    ):
        return
    if artifact.kind == "upload":
        if path != operation.upload_path:
            return
    elif artifact.kind == "staging":
        if path.parent != root / "staging":
            return
    elif path.is_relative_to(root) and path.parent != root / "shards":
        return
    try:
        if _identity(path.parent) != artifact.parent:
            return
        with claim_directory(path.parent) as parent:
            if identity(parent) != (artifact.parent.device, artifact.parent.inode):
                return
            authority = authority_key(f"{operation.id}:{artifact.model_dump_json()}")
            result = remove_entry(
                root,
                authority=authority,
                source_parent=path.parent,
                source_fd=parent,
                name=path.name,
                namespace_parent=path.parent,
                namespace_fd=parent,
                policy=artifact.kind,
            )
            if result is not None:
                return
            if _identity(path) != artifact.identity:
                return
            source = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                value = os.fstat(source)
                expected_type = (
                    stat.S_ISREG(value.st_mode)
                    if artifact.kind == "upload"
                    else stat.S_ISDIR(value.st_mode)
                )
                if (
                    identity(source) != (artifact.identity.device, artifact.identity.inode)
                    or not expected_type
                ):
                    return
                # Keep the originally checked inode alive throughout capture;
                # only the independently validated private capture is disposed.
                remove_entry(
                    root,
                    authority=authority,
                    source_parent=path.parent,
                    source_fd=parent,
                    name=path.name,
                    namespace_parent=path.parent,
                    namespace_fd=parent,
                    policy=artifact.kind,
                    expected=(artifact.identity.device, artifact.identity.inode),
                )
            finally:
                os.close(source)
    except (OSError, ValueError, RuntimeError):
        # Missing, renamed or replaced artifacts and unavailable filesystems are
        # preserved. Records remain available for an idempotent later retry.
        return


def recover_imports(
    lifecycle: DatasetLifecycle | None = None,
    repository: AppStateRepository | None = None,
) -> list[JobRecord]:
    """Reconcile activation, then recover provably dead imports under writer lock.

    Call without other locks held. Lifecycle writer -> operation EX nonblocking
    -> short app-state transactions. Never wait on a live operation's lock.
    """
    lifecycle = lifecycle or DatasetLifecycle()
    repository = repository or AppStateRepository()
    with lifecycle.writer_lock():
        generation = lifecycle.recover_locked(repository, adopt_legacy=False)
        store = lifecycle.root / "imports"
        if not store.exists():
            return []
        _identity(store)
        jobs: list[JobRecord] = []
        for directory in store.iterdir():
            if not _ID.fullmatch(directory.name):
                continue
            fd = -1
            try:
                _identity(directory)
                fd = os.open(directory / "operation.lock", os.O_RDWR | os.O_NOFOLLOW)
                operation = ImportOperation(lifecycle, directory.name, fd)
                record = operation.read_record()
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    if record.job is not None:
                        jobs.append(record.job)
                    continue
                # Re-read after acquiring authority: a live owner may have
                # saved a later state between the first read and lock release.
                record = operation.read_record()
                committed = generation is not None and record.generation_id == generation.dataset.id
                if record.job is not None and (
                    record.job.state in {"queued", "running"}
                    or (committed and record.job.state != "succeeded")
                ):
                    record.job.state = "succeeded" if committed else "failed"
                    record.job.progress = 100 if committed else 0
                    record.job.error = None if committed else _INTERRUPTED
                    record.job.report = (
                        {**(record.job.report or {}), "dataset_version_id": generation.dataset.id}
                        if committed and generation
                        else None
                    )
                    record.job.completed_at = record.job.completed_at or _now()
                record.closed = True
                operation.write_record(record)
                # Durable terminal state precedes cleanup and blocks late workers.
                for artifact in record.artifacts:
                    _remove_artifact(artifact, operation)
                if record.job is not None:
                    jobs.append(record.job)
            except (OSError, ValueError, RuntimeError):
                continue
            finally:
                if fd >= 0:
                    os.close(fd)
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:100]


def load_jobs(lifecycle: DatasetLifecycle | None = None) -> list[JobRecord]:
    """Read validated safe records without cleanup or changing live operations."""
    lifecycle = lifecycle or DatasetLifecycle()
    store = lifecycle.root / "imports"
    if not store.exists():
        return []
    _identity(store)
    jobs: list[JobRecord] = []
    for directory in store.iterdir():
        fd = -1
        try:
            if not _ID.fullmatch(directory.name):
                continue
            _identity(directory)
            fd = os.open(directory / "operation.lock", os.O_RDONLY | os.O_NOFOLLOW)
            operation = ImportOperation(lifecycle, directory.name, fd)
            record = operation.read_record()
            if record.job is not None:
                jobs.append(record.job)
        except (OSError, ValueError, RuntimeError):
            continue
        finally:
            if fd >= 0:
                os.close(fd)
    return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:100]


def cleanup_artifact(operation: ImportOperation, path: Path) -> None:
    """Clean a finished worker's output using its recorded allocation authority."""
    record = operation.read_record()
    for artifact in record.artifacts:
        if artifact.path == str(path):
            _remove_artifact(artifact, operation)
            return


def safe_report(report: dict[str, object]) -> dict[str, object]:
    """Allow measured importer fields; discard arbitrary text and output."""
    safe: dict[str, object] = {}
    mode = report.get("mode")
    if mode in ("v2", "legacy-v1", "legacy-v1-fallback"):
        safe["mode"] = mode
    dataset = report.get("dataset_version_id")
    if isinstance(dataset, str) and re.fullmatch(r"ds_[A-Za-z0-9_]+", dataset):
        safe["dataset_version_id"] = dataset
    for key in ("coverage_start", "coverage_end"):
        if key not in report:
            continue
        value = report[key]
        if value is None or (
            isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        ):
            safe[key] = value
    for key in ("source_size_bytes", "resolved_workers"):
        value = report.get(key)
        if type(value) is int and value >= 0:
            safe[key] = value
    allowed = {
        "counts": {
            "records",
            "record_metadata",
            "hrv_beats",
            "hrv_beats_unparsed",
            "workouts",
            "workout_events",
            "workout_statistics",
            "workout_routes",
            "workout_metadata",
            "activity_summaries",
        },
        "timing_seconds": {"parse_time_seconds", "load_time_seconds", "total_time_seconds"},
    }
    for key, names in allowed.items():
        values = report.get(key)
        if isinstance(values, dict):
            safe[key] = {
                name: value
                for name, value in values.items()
                if name in names
                and type(value) in {int, float}
                and math.isfinite(value)
                and value >= 0
            }
    if "warnings" in report:
        safe["warnings"] = []
    return safe
