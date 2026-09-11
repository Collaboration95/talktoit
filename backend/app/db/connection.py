"""DuckDB connection management.

Provides a single helper for opening the project's database file with
a consistent default path.
"""

from __future__ import annotations

import logging
import os
import threading
import weakref
from pathlib import Path

import duckdb

_DATABASE_LIFECYCLE_LOCK = threading.RLock()
_logger = logging.getLogger(__name__)
_OPEN_CONNECTIONS: weakref.WeakKeyDictionary[duckdb.DuckDBPyConnection, Path] = (
    weakref.WeakKeyDictionary()
)


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
    path = resolve_db_path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    with _DATABASE_LIFECYCLE_LOCK:
        conn = duckdb.connect(str(path), read_only=read_only)
        _OPEN_CONNECTIONS[conn] = path.resolve()
    return conn


def health_database_size_bytes() -> int | None:
    """Return the on-disk health database size, or None when no import exists."""
    path = resolve_db_path()
    return path.stat().st_size if path.exists() else None


def close_open_connections(db_path: str | Path | None = None) -> int:
    """Close tracked connections for a database before replacement/deletion."""
    target = resolve_db_path(db_path).resolve() if db_path is not None else None
    closed = 0
    with _DATABASE_LIFECYCLE_LOCK:
        for conn, opened_path in list(_OPEN_CONNECTIONS.items()):
            if target is not None and opened_path != target:
                continue
            try:
                conn.close()
                closed += 1
            except Exception:
                _logger.debug("Unable to close health database connection", exc_info=True)
            _OPEN_CONNECTIONS.pop(conn, None)
    return closed


def delete_health_database() -> int:
    """Delete the imported health database file after an explicit scoped request.

    Returns the number of files removed (0 or 1). Callers must require explicit
    confirmation; cache, history, saved views, and diagnostics are untouched.
    """
    path = resolve_db_path()
    with _DATABASE_LIFECYCLE_LOCK:
        if not path.exists():
            return 0
        close_open_connections(path)
        try:
            path.unlink()
        except OSError as exc:
            raise RuntimeError(f"Could not remove health database: {exc}") from exc
        return 1
