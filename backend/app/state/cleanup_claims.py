"""Durable POSIX capture before disposal of an originally authorized entry.

Callers serialize one authority with the existing lifecycle/operation ownership.
The claim catalog, exclusive private namespaces and captured objects are trusted:
actors may replace source paths, but must not mutate these private objects/records.
Permissions do not protect against an adversary with the same account or open FDs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

_LIMIT = 1024 * 1024
_ENTRY_LIMIT = 65536
_FORMAT = b"tti-cleanup-claims-v2\n"
_SHARD = re.compile(
    r"(?:records|record_metadata|hrv_beats|workouts|workout_events|workout_statistics|"
    r"workout_routes|workout_metadata|activity_summaries)-[0-9]{4,}-[0-9]{4,}\.parquet\Z"
)
Policy = Literal["generation_file", "legacy_database", "upload", "shards", "staging"]
Identity = tuple[int, int]


class ClaimError(RuntimeError):
    """Ownership is ambiguous; preserve the caller's durable authority."""


def claim_boundary(name: str) -> None:
    """Expose synchronous claim fault seams for artifact subprocess tests."""


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format_version: Literal[2] = 2
    authority: str
    source_parent: str
    parent_identity: Identity
    source_name: str
    expected: Identity
    policy: Policy
    digest: str | None
    namespace: str
    namespace_identity: Identity
    state: Literal["PREPARED", "CAPTURED", "VALIDATED", "CLEANED", "QUARANTINED"]

    @model_validator(mode="after")
    def original_content_proof(self) -> Self:
        if self.policy in {"generation_file", "legacy_database"} and (
            self.digest is None or not re.fullmatch(r"[0-9a-f]{64}", self.digest)
        ):
            raise ValueError("Missing original claim content proof")
        return self


def identity(fd: int) -> Identity:
    """Read the identity of the held object, without resolving a source name."""
    value = os.fstat(fd)
    return value.st_dev, value.st_ino


def authority_key(value: str) -> str:
    """Bound catalog keys to a digest of the caller's original authority."""
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def directory(path: str | Path, *, parent: int | None = None) -> Generator[int, None, None]:
    """Hold a no-follow directory descriptor until all relative IO completes."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ClaimError("Invalid claim directory")
        yield fd
    finally:
        os.close(fd)


def _exists(parent: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _write(fd: int, record: _Record, boundary: Callable[[str], None]) -> None:
    temporary = f"record.{uuid.uuid4().hex}.tmp"
    raw = record.model_dump_json().encode()
    if len(raw) > _LIMIT:
        raise ClaimError("Oversize claim")
    output = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
    )
    try:
        with os.fdopen(output, "wb", closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            boundary(f"claim_{record.state.lower()}_written")
            os.fsync(output)
        boundary(f"claim_{record.state.lower()}_fsynced")
        os.replace(temporary, "record.json", src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
        boundary(f"claim_{record.state.lower()}_committed")
    finally:
        os.close(output)


def _read(fd: int) -> _Record:
    source = os.open("record.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        if not stat.S_ISREG(os.fstat(source).st_mode):
            raise ClaimError("Invalid claim record")
        with os.fdopen(source, "rb", closefd=False) as handle:
            raw = handle.read(_LIMIT + 1)
        if len(raw) > _LIMIT:
            raise ClaimError("Oversize claim record")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ClaimError("Duplicate claim field")
                result[key] = value
            return result

        json.loads(raw, object_pairs_hook=unique)
        return _Record.model_validate_json(raw)
    finally:
        os.close(source)


def _catalog_format(fd: int, *, created: bool) -> None:
    flags = os.O_NOFOLLOW | os.O_NONBLOCK
    flags |= os.O_WRONLY | os.O_CREAT | os.O_EXCL if created else os.O_RDONLY
    marker = os.open("format", flags, 0o600, dir_fd=fd)
    try:
        if not stat.S_ISREG(os.fstat(marker).st_mode):
            raise ClaimError("Invalid claim catalog format")
        with os.fdopen(marker, "wb" if created else "rb", closefd=False) as handle:
            if created:
                handle.write(_FORMAT)
                handle.flush()
                os.fsync(marker)
                os.fsync(fd)
            elif handle.read(64) != _FORMAT:
                raise ClaimError("Unsupported claim catalog format")
    finally:
        os.close(marker)


def _names(fd: int, policy: Policy) -> list[str]:
    names: list[str] = []
    with os.scandir(fd) as entries:
        for entry in entries:
            if len(names) >= _ENTRY_LIMIT:
                raise ClaimError("Oversize captured allocation")
            names.append(entry.name)
    for name in names:
        value = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(value.st_mode):
            raise ClaimError("Unknown captured content")
        if policy == "shards" and not _SHARD.fullmatch(name):
            raise ClaimError("Unknown captured shard")
        if policy == "staging" and name not in {
            "health.duckdb",
            "health.duckdb.wal",
            "manifest.json",
        }:
            raise ClaimError("Unknown captured staging content")
    return names


def _quarantine(
    catalog: int, namespace: int, source: int, record: _Record, boundary: Callable[[str], None]
) -> bool:
    record.state = "QUARANTINED"
    _write(catalog, record, boundary)
    if _exists(namespace, "payload"):
        value = os.stat("payload", dir_fd=namespace, follow_symlinks=False)
        if stat.S_ISREG(value.st_mode):
            try:
                # Atomic create-if-absent only. Retain the quarantine link too:
                # source-name races cannot remove the last preserved copy.
                os.link(
                    "payload",
                    record.source_name,
                    src_dir_fd=namespace,
                    dst_dir_fd=source,
                    follow_symlinks=False,
                )
                os.fsync(source)
            except OSError:
                pass
    return False


def remove_entry(
    root: Path,
    *,
    authority: str,
    source_parent: Path,
    source_fd: int,
    name: str,
    namespace_parent: Path,
    namespace_fd: int,
    policy: Policy,
    expected: Identity | None = None,
    digest: str | None = None,
    validator: Callable[[Path], None] | None = None,
    boundary: Callable[[str], None] | None = None,
) -> bool | None:
    """Replay or capture one entry; None means no existing claim/no new authority.

    A supplied expected identity originates in an original ownership record or
    held, validated FD. An existing claim is immutable authority, never refreshed.
    False preserves proof and a mismatched or uncertain object for manual recovery.
    Complete tombstones remain, preventing recapture of a later source replacement.
    """
    boundary = boundary or claim_boundary
    if name in {"", ".", ".."} or "/" in name or not re.fullmatch(r"[0-9a-f]{64}", authority):
        raise ClaimError("Invalid claim source")
    if (
        not source_parent.is_absolute()
        or not namespace_parent.is_absolute()
        or source_parent.resolve() != source_parent
        or namespace_parent.resolve() != namespace_parent
    ):
        raise ClaimError("Claim paths must be absolute")
    if not stat.S_ISDIR(os.fstat(source_fd).st_mode) or not stat.S_ISDIR(
        os.fstat(namespace_fd).st_mode
    ):
        raise ClaimError("Claim parent must be a held directory")
    if policy == "legacy_database" and validator is None:
        raise ClaimError("Legacy claim requires captured database validation")
    if (
        expected is not None
        and policy in {"generation_file", "legacy_database"}
        and (digest is None or not re.fullmatch(r"[0-9a-f]{64}", digest))
    ):
        raise ClaimError("Generation claim requires original content proof")
    parent_identity = identity(source_fd)
    normalized_name = unicodedata.normalize("NFC", name).casefold()
    key = authority_key(f"{authority}:{parent_identity}:{normalized_name}")
    catalog_root = root / "cleanup-claims"
    if expected is None and not catalog_root.exists():
        return None
    if (
        expected is not None
        and not (catalog_root / key).exists()
        and policy in {"shards", "staging"}
    ):
        # Avoid relocating already-known ambiguous contents. This is only a
        # preflight optimization: capture and repeat validation before disposal.
        with directory(name, parent=source_fd) as candidate:
            if identity(candidate) != expected:
                return False
            try:
                _names(candidate, policy)
            except ClaimError:
                return False
    try:
        catalog_root.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        created = False
    with directory(catalog_root) as catalogs:
        try:
            _catalog_format(catalogs, created=created)
        except FileNotFoundError as exc:
            raise ClaimError("Unproven claim catalog format") from exc
        if created:
            with directory(root) as root_fd:
                os.fsync(root_fd)
        if expected is None and not _exists(catalogs, key):
            return None
        try:
            os.mkdir(key, mode=0o700, dir_fd=catalogs)
            fresh = True
            os.fsync(catalogs)
            with directory(root) as root_fd:
                os.fsync(root_fd)
        except FileExistsError:
            fresh = False
        with directory(key, parent=catalogs) as catalog:
            if fresh:
                if expected is None:
                    # No object is moved and no inode authority is inferred.
                    os.rmdir(key, dir_fd=catalogs)
                    return None
                if expected[0] != parent_identity[0] or identity(namespace_fd)[0] != expected[0]:
                    raise ClaimError("Claim requires same filesystem")
                private = f".tti_claim_{uuid.uuid4().hex}"
                os.mkdir(private, mode=0o700, dir_fd=namespace_fd)
                with directory(private, parent=namespace_fd) as private_fd:
                    os.fsync(private_fd)
                    os.fsync(namespace_fd)
                    record = _Record(
                        authority=authority,
                        source_parent=str(source_parent),
                        parent_identity=parent_identity,
                        source_name=name,
                        expected=expected,
                        policy=policy,
                        digest=digest,
                        namespace=str(namespace_parent / private),
                        namespace_identity=identity(private_fd),
                        state="PREPARED",
                    )
                    _write(catalog, record, boundary)
            else:
                record = _read(catalog)
            if (
                record.authority != authority
                or record.source_parent != str(source_parent)
                or record.parent_identity != parent_identity
                or record.source_name != name
                or record.policy != policy
                or (digest is not None and record.digest != digest)
                or (expected is not None and record.expected != expected)
            ):
                raise ClaimError("Claim authority changed")
            private_path = Path(record.namespace)
            if private_path.parent != namespace_parent or not re.fullmatch(
                r"\.tti_claim_[0-9a-f]{32}", private_path.name
            ):
                raise ClaimError("Invalid private claim namespace")
            with directory(private_path.name, parent=namespace_fd) as private_fd:
                if identity(private_fd) != record.namespace_identity:
                    raise ClaimError("Private claim namespace changed")
                if record.state == "QUARANTINED":
                    return False
                if record.state == "CLEANED":
                    if record.policy in {"shards", "staging"}:
                        if not _exists(private_fd, "payload"):
                            return False
                        with directory("payload", parent=private_fd) as empty:
                            if identity(empty) != record.expected or os.listdir(empty):
                                return False
                    elif _exists(private_fd, "payload"):
                        return False
                    os.fsync(private_fd)
                    os.fsync(source_fd)
                    return not _exists(source_fd, name)
                present = _exists(private_fd, "payload")
                if record.state == "PREPARED":
                    if not present:
                        if not _exists(source_fd, name):
                            return _quarantine(catalog, private_fd, source_fd, record, boundary)
                        boundary("claim_capture_started")
                        # Fresh destination belongs exclusively to this private
                        # namespace. Never overwrite an unexpected payload.
                        if _exists(private_fd, "payload"):
                            raise ClaimError("Claim destination is occupied")
                        os.rename(name, "payload", src_dir_fd=source_fd, dst_dir_fd=private_fd)
                        boundary("claim_captured")
                    os.fsync(source_fd)
                    os.fsync(private_fd)
                    boundary("claim_capture_parents_fsynced")
                    record.state = "CAPTURED"
                    _write(catalog, record, boundary)
                if not _exists(private_fd, "payload"):
                    if record.state != "VALIDATED" or record.policy in {"shards", "staging"}:
                        return _quarantine(catalog, private_fd, source_fd, record, boundary)
                else:
                    captured = os.stat("payload", dir_fd=private_fd, follow_symlinks=False)
                    if not (stat.S_ISDIR(captured.st_mode) or stat.S_ISREG(captured.st_mode)):
                        return _quarantine(catalog, private_fd, source_fd, record, boundary)
                    payload = os.open(
                        "payload",
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=private_fd,
                    )
                    try:
                        value = os.fstat(payload)
                        is_directory = record.policy in {"shards", "staging"}
                        names: list[str] = []
                        matches_type = (
                            stat.S_ISDIR(value.st_mode)
                            if is_directory
                            else stat.S_ISREG(value.st_mode)
                        )
                        if identity(payload) != record.expected or not matches_type:
                            return _quarantine(catalog, private_fd, source_fd, record, boundary)
                        if is_directory:
                            names = _names(payload, record.policy)
                        elif record.digest is not None:
                            with os.fdopen(payload, "rb", closefd=False) as handle:
                                if (
                                    hashlib.file_digest(handle, "sha256").hexdigest()
                                    != record.digest
                                ):
                                    return _quarantine(
                                        catalog, private_fd, source_fd, record, boundary
                                    )
                        if validator is not None:
                            try:
                                validator(private_path / "payload")
                            except (OSError, ValueError, RuntimeError):
                                return _quarantine(catalog, private_fd, source_fd, record, boundary)
                        record.state = "VALIDATED"
                        _write(catalog, record, boundary)
                        boundary("claim_disposal_started")
                        if is_directory:
                            for child in names:
                                os.unlink(child, dir_fd=payload)
                                boundary("claim_child_unlinked")
                            os.fsync(payload)
                        else:
                            os.unlink("payload", dir_fd=private_fd)
                            boundary("claim_file_unlinked")
                    except ClaimError:
                        return _quarantine(catalog, private_fd, source_fd, record, boundary)
                    finally:
                        os.close(payload)
                os.fsync(private_fd)
                os.fsync(source_fd)
                record.state = "CLEANED"
                _write(catalog, record, boundary)
                return not _exists(source_fd, name)
