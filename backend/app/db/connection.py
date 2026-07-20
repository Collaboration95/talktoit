"""DuckDB connection management.

Provides a single helper for opening the project's database file with
a consistent default path.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb


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
    conn = duckdb.connect(str(path), read_only=read_only)
    return conn
