"""DuckDB connection management.

Provides a single helper for opening the project's database file with
a consistent default path.
"""

from __future__ import annotations

import logging
import os
import threading
import weakref
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from app.state.app_state import AppStateRepository, DatasetVersion

if TYPE_CHECKING:
    from app.db.dataset_lifecycle import Generation

_DATABASE_LIFECYCLE_LOCK = threading.RLock()
_logger = logging.getLogger(__name__)
_OPEN_CONNECTIONS: weakref.WeakKeyDictionary[duckdb.DuckDBPyConnection, Path] = (
    weakref.WeakKeyDictionary()
)
# Connections currently being used by a request. A database replacement or
# deletion must never close one of these out from under its caller.
_ACTIVE_LEASES: dict[duckdb.DuckDBPyConnection, int] = {}
_SNAPSHOTS: weakref.WeakKeyDictionary[duckdb.DuckDBPyConnection, DatasetSnapshot] = (
    weakref.WeakKeyDictionary()
)


@dataclass(frozen=True)
class DatasetSnapshot:
    """One request's leased DB, immutable manifest, and allowed route root."""

    connection: duckdb.DuckDBPyConnection
    generation: Generation | None
    manifest: DatasetVersion | None = None
    root: Path | None = None
    source_path: Path | None = None

    @property
    def dataset(self) -> DatasetVersion | None:
        """Return this connection's identity, including explicit no-active-data."""
        return self.generation.dataset if self.generation else self.manifest

    @property
    def export_root(self) -> Path | None:
        """Return only the root belonging to this leased connection."""
        return self.generation.export_root if self.generation else self.root

    @property
    def database_path(self) -> Path | None:
        """Return the leased file privately, or None for empty data."""
        return self.generation.database_path if self.generation else self.source_path


@contextmanager
def dataset_snapshot(
    db_path: str | Path | None = None,
    *,
    allow_legacy: bool = False,
) -> Generator[DatasetSnapshot, None, None]:
    """Acquire a request's complete tuple, preserving arbitrary CLI isolation."""
    from app.db.dataset_lifecycle import DatasetLifecycle

    configured = resolve_db_path().resolve()
    requested = resolve_db_path(db_path).resolve()
    lifecycle = DatasetLifecycle(configured)
    external = requested != configured
    generation = None
    source_path = None
    try:
        with (
            ExitStack() as handles,
            lifecycle.lease() if not external else _no_generation() as generation,
        ):
            if external:
                conn = _open_snapshot_connection(requested)
                source_path = requested
            elif generation:
                conn = _open_snapshot_connection(generation.database_path)
            elif (
                allow_legacy
                and not lifecycle.has_pointer()
                and requested.exists()
                and handles.enter_context(lifecycle.legacy_lease())
            ):
                conn = _open_snapshot_connection(requested)
                source_path = requested
            else:
                conn = _open_snapshot_connection(None)
            snapshot = DatasetSnapshot(conn, generation, source_path=source_path)
            with _DATABASE_LIFECYCLE_LOCK:
                _SNAPSHOTS[conn] = snapshot
            try:
                with lease_connection(conn):
                    yield snapshot
            finally:
                with _DATABASE_LIFECYCLE_LOCK:
                    _SNAPSHOTS.pop(conn, None)
                conn.close()
    finally:
        # Never wait on the writer lock while holding a generation lease or a
        # connection-manager lock. Imports keep the newest rollback generation.
        if generation is not None:
            lifecycle.retire_generation(generation.dataset.id, timeout=0)


def _open_snapshot_connection(path: Path | None) -> duckdb.DuckDBPyConnection:
    from app.db.dataset_lifecycle import DatasetRecoveryError
    from app.db.schema import reset_schema

    conn = None
    try:
        if path is not None:
            return connect(path, read_only=True)
        conn = duckdb.connect(":memory:")
        reset_schema(conn)
        return conn
    except (OSError, duckdb.Error) as exc:
        if conn is not None:
            conn.close()
        raise DatasetRecoveryError() from exc


@contextmanager
def _no_generation() -> Generator[None, None, None]:
    yield None


def snapshot_for_connection(conn: duckdb.DuckDBPyConnection) -> DatasetSnapshot | None:
    """Return registered request metadata without re-reading mutable state."""
    with _DATABASE_LIFECYCLE_LOCK:
        return _SNAPSHOTS.get(conn)


@contextmanager
def bind_dataset_snapshot(snapshot: DatasetSnapshot) -> Generator[DatasetSnapshot, None, None]:
    """Bind an explicitly supplied in-memory tuple for embedded/test consumers.

    Filesystem consumers must use dataset_snapshot() to acquire OS leases.
    This adapter never infers an identity or root from mutable app state.
    """
    conn = snapshot.connection
    with _DATABASE_LIFECYCLE_LOCK:
        previous = _SNAPSHOTS.get(conn)
        _SNAPSHOTS[conn] = snapshot
    try:
        with lease_connection(conn):
            yield snapshot
    finally:
        with _DATABASE_LIFECYCLE_LOCK:
            if previous is None:
                _SNAPSHOTS.pop(conn, None)
            else:
                _SNAPSHOTS[conn] = previous


def connection_dataset(
    conn: duckdb.DuckDBPyConnection,
    repository: AppStateRepository,
) -> DatasetVersion | None:
    """Read identity from a bound tuple; never borrow a SQLite projection."""
    with _DATABASE_LIFECYCLE_LOCK:
        snapshot = _SNAPSHOTS.get(conn)
        if snapshot is not None:
            return snapshot.dataset
    return None


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve the configured health-database location without opening it."""
    if db_path is None:
        db_path = os.environ.get("TTI_DB_PATH")
    if db_path is None:
        this_dir = Path(__file__).resolve().parent
        db_path = this_dir.parent.parent / "data" / "health.duckdb"
    return Path(db_path)


def connect(
    db_path: str | Path | None = None, *, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection to the project database.

    Args:
        db_path: Path to the DuckDB file. Defaults to
            ``backend/data/health.duckdb`` relative to the repo root (two
            levels up from this file). Can be overridden via the
            ``TTI_DB_PATH`` environment variable.
        read_only: Open a shared read-only connection for query-only callers.

    Returns:
        An open DuckDB connection (read/write, auto-commit).
    """
    configured = resolve_db_path(db_path)
    path = resolve_effective_db_path(db_path)
    # Published generations are immutable, including for legacy callers that
    # requested a writable default connection to run migrations.
    read_only = read_only or path != configured
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    with _DATABASE_LIFECYCLE_LOCK:
        conn = duckdb.connect(str(path), read_only=read_only)
        _OPEN_CONNECTIONS[conn] = path.resolve()
    return conn


def resolve_effective_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve managed defaults through the pointer; leave explicit overrides alone."""
    path = resolve_db_path(db_path)
    if path.resolve() != resolve_db_path().resolve():
        return path
    from app.db.dataset_lifecycle import DatasetLifecycle, DatasetRecoveryError

    lifecycle = DatasetLifecycle(path)
    if not lifecycle.root.exists():
        return path
    active = lifecycle.active()
    if active is not None:
        return active.database_path
    if (lifecycle.root / "active.json").exists():
        # A versioned inactive tombstone must never fall back to a legacy DB.
        raise DatasetRecoveryError()
    return path


def health_database_size_bytes() -> int | None:
    """Return the on-disk health database size, or None when no import exists."""
    path = resolve_effective_db_path()
    return path.stat().st_size if path.exists() else None


def close_open_connections(db_path: str | Path | None = None) -> int:
    """Close idle tracked connections for a database before replacement/deletion.

    Connections leased through lease_connection() are in use by another request
    and are left open; they keep reading the previous file until the request
    finishes and the next request opens the replacement.
    """
    target = resolve_db_path(db_path).resolve() if db_path is not None else None
    closed = 0
    with _DATABASE_LIFECYCLE_LOCK:
        for conn, opened_path in list(_OPEN_CONNECTIONS.items()):
            if target is not None and opened_path != target:
                continue
            if _ACTIVE_LEASES.get(conn):
                continue
            try:
                conn.close()
                closed += 1
            except Exception:
                _logger.debug("Unable to close health database connection", exc_info=True)
            _OPEN_CONNECTIONS.pop(conn, None)
    return closed


@contextmanager
def lease_connection(
    conn: duckdb.DuckDBPyConnection,
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Mark a connection as in use for the duration of a request.

    While a lease is held, close_open_connections() (and therefore an import
    activation or a health-data deletion) will not close it.
    """
    with _DATABASE_LIFECYCLE_LOCK:
        _ACTIVE_LEASES[conn] = _ACTIVE_LEASES.get(conn, 0) + 1
    try:
        yield conn
    finally:
        with _DATABASE_LIFECYCLE_LOCK:
            remaining = _ACTIVE_LEASES.get(conn, 1) - 1
            if remaining > 0:
                _ACTIVE_LEASES[conn] = remaining
            else:
                _ACTIVE_LEASES.pop(conn, None)


def delete_health_database(repository: AppStateRepository | None = None) -> int:
    """Commit a no-active tombstone and safely remove unleased managed health DBs."""
    from app.db.dataset_lifecycle import DatasetLifecycle

    return DatasetLifecycle().delete(repository or AppStateRepository())
