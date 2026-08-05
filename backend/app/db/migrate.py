"""Idempotent in-place migrations for the local health DuckDB.

The health database is recreated from scratch during ingestion (DROP + CREATE
in ``app.db.schema``), so an existing database can predate columns that later
code depends on. These migrations repair an already-imported database in place
so read-only API and CLI paths keep working without requiring the original
export to be re-ingested.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from app.db.connection import connect, resolve_db_path

logger = logging.getLogger(__name__)

# Bump when adding a new migration step below.
SCHEMA_VERSION = 1

# Ordered migration steps: (target version, human label, SQL statements).
_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "add records.text_value for typed category values",
        (
            "ALTER TABLE records ADD COLUMN IF NOT EXISTS text_value VARCHAR",
            "CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR)",
        ),
    ),
)


def _current_version(conn: duckdb.DuckDBPyConnection) -> int:
    """Return the recorded schema version, or 0 for an unversioned database."""
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except duckdb.Error:
        return 0
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def migrate(db_path: str | Path | None = None) -> bool:
    """Apply pending migrations to an existing health database, in place.

    Returns True when at least one migration step ran, False when the database
    file does not exist or could not be opened for writing (for example a
    read-only file), so callers can degrade gracefully instead of crashing.
    """
    path = resolve_db_path(db_path)
    if not path.exists():
        return False
    try:
        conn = connect(path, read_only=False)
    except duckdb.Error:
        logger.warning("Health database unavailable for migration; continuing read-only: %s", path)
        return False
    try:
        applied = False
        version = _current_version(conn)
        for target, _label, statements in _MIGRATIONS:
            if version >= target:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (str(target),),
            )
            version = target
            applied = True
        return applied
    except duckdb.Error:
        logger.warning(
            "Health database migration failed; continuing with existing schema.",
            exc_info=True,
        )
        return False
    finally:
        conn.close()


def table_has_column(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    """Return whether ``table`` exposes ``column`` in its live schema."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            [table, column],
        ).fetchone()
    except duckdb.Error:
        return False
    return bool(row and row[0] > 0)
