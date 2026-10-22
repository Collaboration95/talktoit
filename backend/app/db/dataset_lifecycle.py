"""Durable local dataset publication; the versioned pointer is authoritative.

Readers bind immutable generations through cross-process leases. Retirement and
explicit deletion preserve unknown artifacts and never unlink leased data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Literal, Self

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.data_profile import get_data_profile
from app.state.app_state import AppStateRepository, DatasetVersion

_ID = re.compile(r"ds_[0-9a-f]{32}\Z")
_MAX_JSON_BYTES = 1024 * 1024
_TABLES = (
    "records",
    "record_metadata",
    "hrv_beats",
    "workouts",
    "workout_events",
    "workout_statistics",
    "workout_routes",
    "workout_metadata",
    "activity_summaries",
)
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_GenerationId = Annotated[str, Field(pattern=r"^ds_[0-9a-f]{32}$")]


class DatasetRecoveryError(RuntimeError):
    """The durable state cannot safely identify an active dataset."""

    def __init__(self) -> None:
        """Use a safe message without local paths, health values or SQL."""
        super().__init__("Dataset recovery is required. Your local data has been preserved.")


class DatasetBusyError(RuntimeError):
    """A bounded writer/reader wait or safe physical cleanup needs retrying."""

    def __init__(self, *, inactive: bool = False) -> None:
        """Use safe guidance without filesystem or health details."""
        message = (
            "Health data is inactive, but some files could not be removed. "
            "Let active requests finish and retry health deletion."
            if inactive
            else "Health data is busy. Wait for the current import or request and retry."
        )
        super().__init__(message)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Pointer(_StrictModel):
    format_version: Literal[1] = 1
    generation_id: _GenerationId | None
    manifest_sha256: _Digest | None

    @model_validator(mode="after")
    def matching_identity(self) -> Self:
        if (self.generation_id is None) != (self.manifest_sha256 is None):
            raise ValueError("incomplete pointer")
        return self


class _Manifest(_StrictModel):
    format_version: Literal[1] = 1
    dataset: DatasetVersion
    export_root: str
    database_sha256: _Digest

    @model_validator(mode="after")
    def complete_manifest(self) -> Self:
        d = self.dataset
        if (
            not _ID.fullmatch(d.id)
            or d.status != "ready"
            or not d.activated_at
            or not d.imported_at
            or not d.parser_version
            or not d.schema_version
            or d.source_size_bytes < 0
            or d.worker_count < 1
            or not re.fullmatch(r"[0-9a-f]{16}", d.content_hash_prefix)
            or any(type(v) is not int or v < 0 for v in d.counts.values())
            or not all(t in d.counts for t in _TABLES)
            or not Path(self.export_root).is_absolute()
            or str(Path(self.export_root).resolve()) != self.export_root
        ):
            raise ValueError("incomplete manifest")
        return self


class _Journal(_StrictModel):
    format_version: Literal[1] = 1
    previous: _Pointer | None
    next: _Pointer
    legacy_adoption: bool = False


class _Deletion(_StrictModel):
    format_version: Literal[1] = 1
    generations: list[_Pointer]
    legacy: bool


class _Retirement(_StrictModel):
    pointer: _Pointer
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=0)]


class _Retirements(_StrictModel):
    format_version: Literal[1] = 1
    generations: list[_Retirement]

    @model_validator(mode="after")
    def unique_generations(self) -> Self:
        ids = [candidate.pointer.generation_id for candidate in self.generations]
        if None in ids or len(set(ids)) != len(ids):
            raise ValueError("ambiguous retirement identity")
        return self


@dataclass(frozen=True)
class Generation:
    """One validated identity tuple; acquiring a reader lease is future work."""

    dataset: DatasetVersion
    database_path: Path
    export_root: Path


def _hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class DatasetLifecycle:
    """Serialize writers and recover a database, manifest and root together."""

    def __init__(self, target: Path | None = None) -> None:
        """Namespace the managed store by the canonical configured DB filename."""
        if target is None:
            from app.db.connection import resolve_db_path

            target = resolve_db_path()
        self.target = target.resolve()
        self.root = self.target.with_name(f"{self.target.name}.datasets")

    def _boundary(self, name: str) -> None:
        """Expose synchronous fault boundaries for subprocess regression tests."""

    def _safe(self, path: Path) -> Path:
        if not path.is_relative_to(self.root):
            raise DatasetRecoveryError()
        for component in (path, *path.parents):
            if not component.is_relative_to(self.root):
                break
            if component.is_symlink():
                raise DatasetRecoveryError()
        return path

    def _layout(self) -> None:
        self._safe(self.root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ("generations", "staging", "leases"):
            self._safe(self.root / name).mkdir(mode=0o700, exist_ok=True)
        _fsync_directory(self.root)
        _fsync_directory(self.root.parent)

    @contextmanager
    def writer_lock(self, timeout: float | None = None) -> Generator[None, None, None]:
        """Take the stable mandatory POSIX writer lock before any other locks."""
        import fcntl

        self._layout()
        fd = os.open(
            self._safe(self.root / "lifecycle.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DatasetRecoveryError()
            self._lock(fd, fcntl.LOCK_EX, timeout)
            yield
        finally:
            # Closing the descriptor also releases the lock after exceptions.
            os.close(fd)

    @staticmethod
    def _lock(fd: int, operation: int, timeout: float | None) -> None:
        import fcntl

        if timeout is None:
            fcntl.flock(fd, operation)
            return
        deadline = time.monotonic() + max(0, timeout)
        while True:
            try:
                fcntl.flock(fd, operation | fcntl.LOCK_NB)
                return
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise DatasetBusyError() from exc
                time.sleep(min(0.005, max(0, deadline - time.monotonic())))

    def has_pointer(self) -> bool:
        """Return whether activation or explicit deletion has a durable record."""
        return self._safe(self.root / "active.json").exists()

    @contextmanager
    def legacy_lease(self) -> Generator[bool, None, None]:
        """Serialize unassociated legacy CLI reads with import and deletion."""
        import fcntl

        self._layout()
        fd = os.open(
            self._safe(self.root / "lifecycle.lock"),
            os.O_CREAT | os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DatasetRecoveryError()
            self._lock(fd, fcntl.LOCK_SH, 0.25)
            yield not self.has_pointer()
        finally:
            os.close(fd)

    @contextmanager
    def lease(self, *, timeout: float = 0.25) -> Generator[Generation | None, None, None]:
        """Acquire one immutable generation with a pointer/lease/reread protocol.

        Never create a lease inode here. Retirement may win before acquisition;
        release and retry from the pointer instead of mixing generation parts.
        """
        import fcntl

        for _ in range(4):
            pointer = self._pointer()
            self._boundary("snapshot_pointer_read")
            if pointer is None or pointer.generation_id is None:
                if self._pointer() == pointer:
                    yield None
                    return
                continue
            fd = None
            try:
                path = self._safe(self.root / "leases" / f"{pointer.generation_id}.lock")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise DatasetRecoveryError()
                self._lock(fd, fcntl.LOCK_SH, timeout)
                self._boundary("snapshot_leased")
                if self._pointer() != pointer:
                    continue
                generation = self._generation(pointer)
                self._boundary("snapshot_validated")
                yield generation
                return
            except FileNotFoundError as exc:
                if self._pointer() == pointer:
                    raise DatasetRecoveryError() from exc
            finally:
                if fd is not None:
                    os.close(fd)
        raise DatasetBusyError()

    def protected_generation_ids(self) -> frozenset[str]:
        """Return references cleanup must preserve; callers hold the writer lock."""
        pointers = [self._pointer()]
        retained = self._safe(self.root / "retained.json")
        if retained.exists():
            pointers.append(self._read_pointer(retained))
        journal = self._safe(self.root / "transaction.json")
        if journal.exists():
            record = self._read(journal, _Journal)
            assert isinstance(record, _Journal)  # noqa: S101
            pointers.extend([record.previous, record.next])
        deletion = self._safe(self.root / "deletion.json")
        if deletion.exists():
            intent = self._read(deletion, _Deletion)
            assert isinstance(intent, _Deletion)  # noqa: S101
            pointers.extend(intent.generations)
        return frozenset(p.generation_id for p in pointers if p and p.generation_id)

    def _validate_retained(self) -> None:
        retained = self._safe(self.root / "retained.json")
        if retained.exists() and self._read_pointer(retained).generation_id is None:
            raise DatasetRecoveryError()

    def generation_is_leased(self, generation_id: str) -> bool:
        """Conservatively test a stable lease inode without creating/replacing it."""
        import fcntl

        if not _ID.fullmatch(generation_id):
            raise DatasetRecoveryError()
        try:
            fd = os.open(
                self._safe(self.root / "leases" / f"{generation_id}.lock"),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            )
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    return True
                self._lock(fd, fcntl.LOCK_EX, 0)
                return False
            finally:
                os.close(fd)
        except (OSError, DatasetBusyError, DatasetRecoveryError):
            return True

    def new_staging(self) -> Path:
        """Create a unique private staging child while the writer lock is held."""
        path = self._safe(self.root / "staging" / uuid.uuid4().hex)
        path.mkdir(mode=0o700)
        self._boundary("staging_created")
        return path / "health.duckdb"

    def _read(self, path: Path, model: type[_StrictModel]) -> _StrictModel:
        try:
            if not stat.S_ISREG(self._safe(path).stat().st_mode):
                raise DatasetRecoveryError()
            with self._safe(path).open("rb") as handle:
                raw = handle.read(_MAX_JSON_BYTES + 1)
            if len(raw) > _MAX_JSON_BYTES:
                raise ValueError("oversize record")

            # Reject duplicate keys rather than silently choosing one identity.
            def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate field")
                    result[key] = value
                return result

            json.loads(raw, object_pairs_hook=unique)
            return model.model_validate_json(raw)
        except (OSError, ValueError, ValidationError) as exc:
            raise DatasetRecoveryError() from exc

    def _pointer(self) -> _Pointer | None:
        path = self._safe(self.root / "active.json")
        return self._read_pointer(path) if path.exists() else None

    def _read_pointer(self, path: Path) -> _Pointer:
        record = self._read(path, _Pointer)
        assert isinstance(record, _Pointer)  # noqa: S101
        return record

    def _generation(self, pointer: _Pointer, *, verify_database: bool = False) -> Generation | None:
        if pointer.generation_id is None:
            return None
        directory = self._safe(self.root / "generations" / pointer.generation_id)
        path = self._safe(directory / "manifest.json")
        try:
            if _hash_file(path) != pointer.manifest_sha256:
                raise DatasetRecoveryError()
            manifest = self._read(path, _Manifest)
            assert isinstance(manifest, _Manifest)  # noqa: S101
            if manifest.dataset.id != pointer.generation_id:
                raise DatasetRecoveryError()
            database = self._safe(directory / "health.duckdb")
            lease = self._safe(self.root / "leases" / f"{pointer.generation_id}.lock")
            if not database.is_file() or not lease.is_file():
                raise DatasetRecoveryError()
            if self._safe(database.with_suffix(".duckdb.wal")).exists():
                raise DatasetRecoveryError()
            if verify_database:
                if _hash_file(database) != manifest.database_sha256:
                    raise DatasetRecoveryError()
                self._validate_database(database, manifest.dataset)
            return Generation(manifest.dataset, database, Path(manifest.export_root))
        except OSError as exc:
            raise DatasetRecoveryError() from exc

    def active(self) -> Generation | None:
        """Read the pointer and immutable metadata without inventing an identity."""
        pointer = self._pointer()
        return self._generation(pointer) if pointer is not None else None

    def _validate_database(self, path: Path, dataset: DatasetVersion) -> None:
        try:
            with duckdb.connect(str(path), read_only=True) as conn:
                for table in _TABLES:
                    if conn.execute(f"SELECT count(*) FROM {table}").fetchone() != (  # noqa: S608
                        dataset.counts[table],
                    ):
                        raise DatasetRecoveryError()
                for child in _TABLES[1:3] + _TABLES[4:8]:
                    parent, key = (
                        ("records", "record_id")
                        if child in _TABLES[1:3]
                        else ("workouts", "workout_id")
                    )
                    if conn.execute(  # identifiers come only from the closed table whitelist
                        f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p "  # noqa: S608
                        f"ON c.{key} = p.id WHERE p.id IS NULL"
                    ).fetchone() != (0,):
                        raise DatasetRecoveryError()
                profile = get_data_profile(conn)
                start = profile.first_date.isoformat() if profile.first_date else None
                end = profile.latest_date.isoformat() if profile.latest_date else None
                if (dataset.coverage_start, dataset.coverage_end) != (start, end):
                    raise DatasetRecoveryError()
        except (duckdb.Error, KeyError) as exc:
            raise DatasetRecoveryError() from exc

    def _write(self, path: Path, record: _StrictModel, phase: str) -> None:
        with self._safe(path).open("xb") as handle:
            handle.write(record.model_dump_json().encode())
            handle.flush()
            self._boundary(f"{phase}_written")
            os.fsync(handle.fileno())
        self._boundary(f"{phase}_fsynced")

    def activate(
        self,
        staging: Path,
        dataset: DatasetVersion,
        export_root: Path,
        repository: AppStateRepository,
        *,
        legacy_adoption: bool = False,
    ) -> Generation:
        """Publish closed staging data under the writer lock, then commit once.

        Before pointer replacement any exception leaves the old pointer intact.
        After replacement never undo it: recovery validates and durably repairs
        the projection even if the directory fsync or SQLite operation failed.
        """
        staging = self._safe(staging)
        self._boundary("database_closed")
        if staging.parent.parent != self.root / "staging":
            raise DatasetRecoveryError()
        manifest = _Manifest(
            dataset=dataset,
            export_root=str(export_root.resolve()),
            database_sha256=_hash_file(staging),
        )
        self._validate_database(staging, dataset)
        with staging.open("rb") as handle:
            os.fsync(handle.fileno())
        self._boundary("database_fsynced")
        manifest_path = staging.parent / "manifest.json"
        self._write(manifest_path, manifest, "manifest")
        _fsync_directory(staging.parent)
        _fsync_directory(staging.parent.parent)
        self._boundary("staging_fsynced")
        destination = self._safe(self.root / "generations" / dataset.id)
        if destination.exists():
            raise DatasetRecoveryError()
        os.rename(staging.parent, destination)
        self._boundary("generation_renamed")
        _fsync_directory(self.root / "staging")
        _fsync_directory(self.root / "generations")
        self._boundary("generation_fsynced")
        with self._safe(self.root / "leases" / f"{dataset.id}.lock").open("xb") as handle:
            os.fsync(handle.fileno())
        _fsync_directory(self.root / "leases")
        self._boundary("lease_fsynced")
        pointer = _Pointer(
            generation_id=dataset.id, manifest_sha256=_hash_file(destination / "manifest.json")
        )
        journal = _Journal(previous=self._pointer(), next=pointer, legacy_adoption=legacy_adoption)
        temporary = self.root / f"transaction.json.tmp.{uuid.uuid4().hex}"
        self._write(temporary, journal, "journal")
        os.replace(temporary, self._safe(self.root / "transaction.json"))
        _fsync_directory(self.root)
        self._boundary("journal_committed")
        temporary = self.root / f"active.json.tmp.{uuid.uuid4().hex}"
        self._write(temporary, pointer, "pointer")
        os.replace(temporary, self._safe(self.root / "active.json"))
        self._boundary("pointer_replaced")
        _fsync_directory(self.root)
        self._boundary("pointer_committed")
        self._boundary("projection_started")
        repository.project_generation(dataset, export_root)
        self._boundary("projection_committed")
        self._finish_journal()
        self._drain_retirements()
        return Generation(dataset, destination / "health.duckdb", export_root.resolve())

    def _finish_journal(self) -> None:
        self._validate_retained()
        path = self._safe(self.root / "transaction.json")
        if not path.exists():
            return
        journal = self._read(path, _Journal)
        assert isinstance(journal, _Journal)  # noqa: S101
        if self._pointer() == journal.next:
            retained = self._safe(self.root / "retained.json")
            replacement = (
                journal.previous
                if (
                    journal.next.generation_id
                    and journal.previous
                    and journal.previous.generation_id
                )
                else None
            )
            if retained.exists():
                former = self._read_pointer(retained)
                if former != replacement:
                    # Persist proof before losing the only reference to a
                    # formerly committed rollback copy. Replays never infer
                    # eligibility from unreferenced generation directories.
                    self._queue_retirement(former)
            if journal.next.generation_id and journal.previous and journal.previous.generation_id:
                self._replace_record(retained, journal.previous, "retained")
            else:
                retained.unlink(missing_ok=True)
                self._boundary("retained_cleared")
                _fsync_directory(self.root)
        path.unlink()
        self._boundary("journal_unlinked")
        _fsync_directory(self.root)
        self._boundary("journal_removed")

    def _retirements(self) -> _Retirements:
        path = self._safe(self.root / "retirement.json")
        if not path.exists():
            return _Retirements(generations=[])
        record = self._read(path, _Retirements)
        assert isinstance(record, _Retirements)  # noqa: S101
        return record

    def _queue_retirement(self, pointer: _Pointer) -> None:
        record = self._retirements()
        for candidate in record.generations:
            if candidate.pointer.generation_id == pointer.generation_id:
                if candidate.pointer != pointer:
                    raise DatasetRecoveryError()
                return  # Never replace the original directory identity on replay.
        directory = self._safe(self.root / "generations" / str(pointer.generation_id))
        identity = directory.stat()
        if not stat.S_ISDIR(identity.st_mode):
            raise DatasetRecoveryError()
        record.generations.append(
            _Retirement(pointer=pointer, device=identity.st_dev, inode=identity.st_ino)
        )
        if len(record.model_dump_json().encode()) > _MAX_JSON_BYTES:
            raise DatasetRecoveryError()
        self._replace_record(self.root / "retirement.json", record, "retirement_candidate")

    def _drain_retirements(self, timeout: float = 0.0) -> None:
        """Retry only recorded rollback copies under the already-held writer lock."""
        record = self._retirements()
        protected = self.protected_generation_ids()
        remaining = []
        for candidate in record.generations:
            pointer = candidate.pointer
            try:
                if pointer.generation_id in protected:
                    remaining.append(candidate)
                    continue
                directory = self._safe(self.root / "generations" / str(pointer.generation_id))
                if directory.exists():
                    identity = directory.stat()
                    if (identity.st_dev, identity.st_ino) != (candidate.device, candidate.inode):
                        raise DatasetRecoveryError()
                self._boundary("retirement_cleanup_started")
                self._remove_generation(pointer, timeout)
                # Also flush an already-missing directory after a prior crash
                # between rmdir and its parent fsync, before forgetting proof.
                _fsync_directory(self.root / "generations")
                self._boundary("retirement_generation_removed")
            except (OSError, DatasetBusyError, DatasetRecoveryError):
                remaining.append(candidate)
        if remaining != record.generations:
            try:
                self._replace_record(
                    self.root / "retirement.json",
                    _Retirements(generations=remaining),
                    "retirement_drained",
                )
            except OSError:
                # The old durable candidates remain sufficient for retry if
                # pruning fails. Never undo a successfully reconciled import.
                pass

    def _replace_record(self, path: Path, record: _StrictModel, phase: str) -> None:
        temporary = self.root / f"{path.name}.tmp.{uuid.uuid4().hex}"
        self._write(temporary, record, phase)
        os.replace(temporary, self._safe(path))
        self._boundary(f"{phase}_replaced")
        _fsync_directory(self.root)
        self._boundary(f"{phase}_committed")

    def _remove_generation(self, pointer: _Pointer, timeout: float) -> int:
        import fcntl

        if pointer.generation_id is None:
            return 0
        directory = self._safe(self.root / "generations" / pointer.generation_id)
        if not directory.exists():
            return 0
        if any(p.name not in {"health.duckdb", "manifest.json"} for p in directory.iterdir()):
            raise DatasetBusyError(inactive=True)
        fd = os.open(
            self._safe(self.root / "leases" / f"{pointer.generation_id}.lock"),
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DatasetRecoveryError()
            self._lock(fd, fcntl.LOCK_EX, timeout)
            manifest_path = self._safe(directory / "manifest.json")
            database = self._safe(directory / "health.duckdb")
            if manifest_path.exists():
                if _hash_file(manifest_path) != pointer.manifest_sha256:
                    raise DatasetRecoveryError()
                record = self._read(manifest_path, _Manifest)
                assert isinstance(record, _Manifest)  # noqa: S101
                if record.dataset.id != pointer.generation_id:
                    raise DatasetRecoveryError()
                if database.exists() and (
                    not database.is_file() or _hash_file(database) != record.database_sha256
                ):
                    raise DatasetRecoveryError()
            elif database.exists():
                raise DatasetRecoveryError()
            # Close only idle handles; OS leases exclude all snapshot readers.
            from app.db.connection import close_open_connections

            close_open_connections(database)
            removed = int(database.exists())
            database.unlink(missing_ok=True)
            self._boundary("deletion_database_unlinked")
            manifest_path.unlink(missing_ok=True)
            self._boundary("generation_manifest_unlinked")
            directory.rmdir()
            self._boundary("generation_directory_removed")
            _fsync_directory(self.root / "generations")
            return removed
        finally:
            os.close(fd)

    def retire_generation(self, generation_id: str, *, timeout: float = 0.0) -> bool:
        """Retire a superseded copy only after leases drain; retain rollback data."""
        if not _ID.fullmatch(generation_id):
            raise DatasetRecoveryError()
        try:
            current = self._pointer()
            if current is not None and current.generation_id == generation_id:
                return False
            with self.writer_lock(timeout=timeout):
                if generation_id in self.protected_generation_ids():
                    return False
                self._drain_retirements(timeout)
                return not self._safe(self.root / "generations" / generation_id).exists()
        except (OSError, DatasetBusyError, DatasetRecoveryError):
            return False

    def delete(self, repository: AppStateRepository, *, timeout: float = 0.5) -> int:
        """Commit inactivity before bounded, lease-protected physical deletion.

        An unresolved file remains inactive and retryable; unrelated SQLite
        history, saved views, diagnostics and cache entries are independent.
        """
        with self.writer_lock(timeout=timeout):
            pointer = self._pointer()
            intent_path = self._safe(self.root / "deletion.json")
            intent = self._read(intent_path, _Deletion) if intent_path.exists() else None
            if intent is not None:
                assert isinstance(intent, _Deletion)  # noqa: S101
            candidates = {p.generation_id: p for p in intent.generations} if intent else {}
            if pointer is not None and pointer.generation_id:
                candidates[pointer.generation_id] = pointer
            retained = self._safe(self.root / "retained.json")
            if retained.exists():
                previous = self._read_pointer(retained)
                if previous.generation_id:
                    candidates[previous.generation_id] = previous
            for directory in (self.root / "generations").iterdir():
                if not _ID.fullmatch(directory.name):
                    continue
                path = self._safe(directory / "manifest.json")
                if directory.name in candidates:
                    continue
                # A recognized complete manifest proves an exact managed child;
                # unknown or extra content is never recursively traversed.
                record = self._read(path, _Manifest)
                assert isinstance(record, _Manifest)  # noqa: S101
                if record.dataset.id != directory.name:
                    raise DatasetRecoveryError()
                candidates[directory.name] = _Pointer(
                    generation_id=directory.name, manifest_sha256=_hash_file(path)
                )
            intent = _Deletion(
                generations=list(candidates.values()),
                legacy=self.target.exists() or bool(intent and intent.legacy),
            )
            self._replace_record(intent_path, intent, "deletion_intent")
            if pointer is None or pointer.generation_id is not None:
                tombstone = _Pointer(generation_id=None, manifest_sha256=None)
                journal = _Journal(previous=pointer, next=tombstone)
                self._replace_record(self.root / "transaction.json", journal, "deletion_journal")
                self._replace_record(self.root / "active.json", tombstone, "deletion_pointer")
                self._boundary("deletion_pointer_committed")
            repository.deactivate_active_dataset()
            self._boundary("deletion_projected")
            self._finish_journal()
            removed = self._complete_deletion(intent, timeout)
            self._drain_retirements()
            return removed

    def _complete_deletion(self, intent: _Deletion, timeout: float) -> int:
        removed = 0
        failed = False
        deadline = time.monotonic() + timeout
        for pointer in intent.generations:
            try:
                removed += self._remove_generation(pointer, max(0, deadline - time.monotonic()))
            except (OSError, DatasetRecoveryError, DatasetBusyError):
                failed = True
        if intent.legacy:
            from app.db.connection import close_open_connections

            close_open_connections(self.target)
            try:
                if self.target.exists():
                    # Explicit health scope authorizes the imported DB, not an
                    # export/GPX or unrelated file under a misconfigured name.
                    with duckdb.connect(str(self.target), read_only=True) as legacy:
                        tables = {
                            str(row[0])
                            for row in legacy.execute(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema = 'main'"
                            ).fetchall()
                        }
                        if not set(_TABLES).issubset(tables):
                            raise DatasetRecoveryError()
                    self.target.unlink()
                    _fsync_directory(self.target.parent)
                    removed += 1
            except (OSError, duckdb.Error, DatasetRecoveryError):
                failed = True
        if failed:
            raise DatasetBusyError(inactive=True)
        self._safe(self.root / "deletion.json").unlink(missing_ok=True)
        _fsync_directory(self.root)
        self._boundary("deletion_finished")
        return removed

    def recover(self, repository: AppStateRepository) -> Generation | None:
        """Recover before health migrations or provider startup; repeat safely."""
        with self.writer_lock():
            return self.recover_locked(repository)

    def recover_locked(
        self,
        repository: AppStateRepository,
        *,
        adopt_legacy: bool = True,
    ) -> Generation | None:
        """Recover under an already-held writer lock (also used by the importer)."""
        self._validate_retained()
        self._retirements()  # Unknown cleanup authority fails closed before activation.
        pointer = self._pointer()
        journal_path = self._safe(self.root / "transaction.json")
        journal = self._read(journal_path, _Journal) if journal_path.exists() else None
        if journal is not None:
            assert isinstance(journal, _Journal)  # noqa: S101
            if pointer != journal.previous and pointer != journal.next:
                raise DatasetRecoveryError()
            if pointer is None and journal.legacy_adoption:
                # Pre-commit adoption still has its original DB + SQLite
                # manifest. Do not clear that only proven legacy identity.
                self._finish_journal()
                return self._adopt_legacy(repository)
        if pointer is None and journal is None:
            if adopt_legacy and (self.target.exists() or repository.get_active() is not None):
                return self._adopt_legacy(repository)
            return None
        try:
            generation = self._generation(pointer, verify_database=True) if pointer else None
        except DatasetRecoveryError:
            # Only a valid journal proves which previous pointer may be restored.
            if not isinstance(journal, _Journal) or journal.previous is None:
                raise
            generation = self._generation(journal.previous, verify_database=True)
            temporary = self.root / f"active.json.tmp.{uuid.uuid4().hex}"
            self._write(temporary, journal.previous, "restore")
            os.replace(temporary, self.root / "active.json")
        self._boundary("recovery_validated")
        _fsync_directory(self.root)
        self._boundary("recovery_pointer_fsynced")
        if generation is None:
            repository.deactivate_active_dataset()
        else:
            repository.project_generation(generation.dataset, generation.export_root)
        self._boundary("recovery_projected")
        self._finish_journal()
        self._drain_retirements()
        if generation is None:
            deletion = self._safe(self.root / "deletion.json")
            if deletion.exists():
                intent = self._read(deletion, _Deletion)
                assert isinstance(intent, _Deletion)  # noqa: S101
                try:
                    self._complete_deletion(intent, 0)
                except DatasetBusyError:
                    pass
        self._boundary("recovery_finished")
        return generation

    def _adopt_legacy(self, repository: AppStateRepository) -> Generation:
        dataset = repository.get_active()
        root = repository.get_export_root()
        if dataset is None or root is None or not self.target.is_file() or self.target.is_symlink():
            raise DatasetRecoveryError()
        if self.target.with_suffix(self.target.suffix + ".wal").exists():
            raise DatasetRecoveryError()
        self._validate_database(self.target, dataset)
        # Never move the sole legacy copy. Old schema migration, if necessary,
        # runs only on this private copy before immutable publication.
        staging = self.new_staging()
        shutil.copyfile(self.target, staging)
        from app.db.migrate import migrate

        migrate(staging)
        # Interrupted adoption may have published an inactive copy already.
        # A fresh id avoids inferring reuse or overwriting that retained copy.
        dataset = replace(dataset, id=f"ds_{uuid.uuid4().hex}")
        return self.activate(staging, dataset, root, repository, legacy_adoption=True)
