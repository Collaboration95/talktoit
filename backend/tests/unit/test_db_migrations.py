"""In-place schema migrations must repair pre-text_value databases idempotently."""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.db.migrate import SCHEMA_VERSION, migrate, table_has_column

_SQL_LEGACY_SCHEMA = """
CREATE TABLE records (
    id            INTEGER PRIMARY KEY,
    type          VARCHAR NOT NULL,
    source_name   VARCHAR NOT NULL,
    source_version VARCHAR,
    device        VARCHAR,
    unit          VARCHAR,
    creation_date TIMESTAMP,
    start_date    TIMESTAMP NOT NULL,
    end_date      TIMESTAMP NOT NULL,
    value         DOUBLE
);
"""


def _write_legacy_database(path: Path) -> None:
    """Create a database matching the pre-text_value records schema."""
    conn = duckdb.connect(str(path))
    conn.execute(_SQL_LEGACY_SCHEMA)
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKQuantityTypeIdentifierStepCount', 'Watch', NULL, NULL, 'count', NULL,
         '2026-06-01 07:00:00', '2026-06-01 08:00:00', 1234.0)"""
    )
    conn.close()


def _column_names(path: Path) -> list[str]:
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return [row[0] for row in conn.execute("DESCRIBE records").fetchall()]
    finally:
        conn.close()


def test_migrate_adds_text_value_to_legacy_database(tmp_path: Path) -> None:
    """Migration adds the column without touching existing numeric rows."""
    db_path = tmp_path / "health.duckdb"
    _write_legacy_database(db_path)

    changed = migrate(db_path)

    assert changed is True
    assert "text_value" in _column_names(db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        assert conn.execute("SELECT value FROM records WHERE id = 1").fetchone() == (1234.0,)
        assert conn.execute("SELECT text_value FROM records WHERE id = 1").fetchone() == (None,)
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert version == (str(SCHEMA_VERSION),)
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    """Re-running the migration is a no-op and keeps the schema intact."""
    db_path = tmp_path / "health.duckdb"
    _write_legacy_database(db_path)

    assert migrate(db_path) is True
    assert migrate(db_path) is False
    assert "text_value" in _column_names(db_path)


def test_migrate_skips_missing_database(tmp_path: Path) -> None:
    """A database that does not exist is not created as a side effect."""
    assert migrate(tmp_path / "does-not-exist.duckdb") is False


def test_migrate_records_version_on_current_schema(tmp_path: Path) -> None:
    """A current-schema database gets version bookkeeping on first run only."""
    db_path = tmp_path / "health.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE records (id INTEGER, text_value VARCHAR, value DOUBLE)")
    conn.close()

    assert migrate(db_path) is True
    assert migrate(db_path) is False
    assert "text_value" in _column_names(db_path)


def test_migrate_does_not_crash_on_read_only_database(tmp_path: Path) -> None:
    """A read-only file degrades to a graceful no-op, never an exception."""
    import os
    import stat

    db_path = tmp_path / "health.duckdb"
    _write_legacy_database(db_path)
    os.chmod(db_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        assert migrate(db_path) is False
    finally:
        os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def test_table_has_column_detects_missing_and_present_columns(tmp_path: Path) -> None:
    """The schema probe drives the graceful capability fallback."""
    legacy_path = tmp_path / "legacy.duckdb"
    _write_legacy_database(legacy_path)
    legacy = duckdb.connect(str(legacy_path), read_only=True)
    try:
        assert table_has_column(legacy, "records", "text_value") is False
        assert table_has_column(legacy, "records", "value") is True
    finally:
        legacy.close()

    migrate(legacy_path)
    upgraded = duckdb.connect(str(legacy_path), read_only=True)
    try:
        assert table_has_column(upgraded, "records", "text_value") is True
    finally:
        upgraded.close()


async def test_fastapi_lifespan_runs_health_db_migrations(monkeypatch) -> None:
    """App startup repairs the health schema before serving requests."""
    import app.main as main_module

    class _FakeGateway:
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    calls: list[str] = []
    gateway = _FakeGateway()
    monkeypatch.setattr(main_module, "migrate", lambda: calls.append("migrate"))
    monkeypatch.setattr(main_module, "make_provider_gateway", lambda: gateway)

    app = main_module.create_app()
    async with main_module._lifespan(app):
        assert app.state.provider_gateway is gateway

    assert calls == ["migrate"]
    assert gateway.closed
