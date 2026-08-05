"""Legacy (pre-text_value) databases must degrade gracefully on dashboard panels."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dashboard import get_capabilities, get_sleep_stages
from app.db.migrate import migrate
from app.main import app

# Faithful pre-text_value schema: only the tables the dashboard queries, with
# the records table still lacking the typed-category text_value column.
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
CREATE TABLE workouts (
    id              INTEGER PRIMARY KEY,
    activity_type   VARCHAR NOT NULL,
    duration        DOUBLE,
    duration_unit   VARCHAR,
    source_name     VARCHAR NOT NULL,
    source_version  VARCHAR,
    device          VARCHAR,
    creation_date   TIMESTAMP,
    start_date      TIMESTAMP NOT NULL,
    end_date        TIMESTAMP NOT NULL
);
CREATE TABLE activity_summaries (
    date_components          VARCHAR PRIMARY KEY,
    active_energy_burned     DOUBLE,
    active_energy_burned_goal DOUBLE,
    active_energy_burned_unit VARCHAR,
    apple_move_time          DOUBLE,
    apple_move_time_goal     DOUBLE,
    apple_exercise_time      DOUBLE,
    apple_exercise_time_goal DOUBLE,
    apple_stand_hours        INTEGER,
    apple_stand_hours_goal   INTEGER
);
CREATE INDEX idx_records_type_date ON records(type, start_date);
"""


def _legacy_conn() -> duckdb.DuckDBPyConnection:
    """In-memory database matching the pre-text_value records schema."""
    conn = duckdb.connect(":memory:")
    conn.execute(_SQL_LEGACY_SCHEMA)
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL, NULL,
         '2026-06-01 22:00:00', '2026-06-01 23:00:00', NULL),
        (2, 'HKQuantityTypeIdentifierStepCount', 'Watch', NULL, NULL, 'count', NULL,
         '2026-06-01 07:00:00', '2026-06-01 08:00:00', 1234.0)"""
    )
    return conn


def _write_legacy_database(path: Path) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(_SQL_LEGACY_SCHEMA)
    conn.execute(
        """INSERT INTO records VALUES
        (1, 'HKCategoryTypeIdentifierSleepAnalysis', 'Watch', NULL, NULL, NULL, NULL,
         '2026-06-01 22:00:00', '2026-06-01 23:00:00', NULL)"""
    )
    conn.close()


def test_sleep_stages_degrade_gracefully_without_text_value_column() -> None:
    """A stale database reports absent stage labels instead of raising."""
    conn = _legacy_conn()
    response = get_sleep_stages(
        start=datetime(2026, 6, 1).date(), end=datetime(2026, 6, 2).date(), conn=conn
    )

    assert not response.stage_data_available
    assert response.stages_hours == {}
    assert "not available" in response.message


def test_capabilities_degrade_gracefully_without_text_value_column() -> None:
    """Numeric metrics stay available; category metrics cannot prove text values."""
    conn = _legacy_conn()
    response = get_capabilities(conn=conn)
    caps = {item.name: item for item in response.capabilities}

    assert caps["steps"].present is True
    assert caps["steps"].state == "available"
    assert caps["sleep"].present is False
    assert caps["sleep"].state == "malformed"


def test_capabilities_legacy_schema_scoped_window_still_works() -> None:
    """The windowed capability query also survives the legacy schema."""
    conn = _legacy_conn()
    response = get_capabilities(
        start=datetime(2026, 6, 1).date(), end=datetime(2026, 6, 2).date(), conn=conn
    )
    caps = {item.name: item for item in response.capabilities}

    assert caps["steps"].state == "available"
    assert caps["sleep"].state == "malformed"


def test_migrated_legacy_database_serves_sleep_stages(tmp_path: Path) -> None:
    """After the in-place migration the panel works; labels stay absent."""
    db_path = tmp_path / "health.duckdb"
    _write_legacy_database(db_path)
    assert migrate(db_path) is True

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        response = get_sleep_stages(
            start=datetime(2026, 6, 1).date(), end=datetime(2026, 6, 2).date(), conn=conn
        )
    finally:
        conn.close()

    assert not response.stage_data_available
    assert response.total_asleep_hours == 0.0
    assert "not available" in response.message


def _override_conn(conn: duckdb.DuckDBPyConnection) -> Generator[None, None, None]:
    from contextlib import contextmanager

    from app.api.dashboard import _get_conn

    @contextmanager
    def _override() -> Generator[None, None, None]:
        def _dependency() -> Generator[duckdb.DuckDBPyConnection, None, None]:
            yield conn

        app.dependency_overrides[_get_conn] = _dependency
        try:
            yield
        finally:
            app.dependency_overrides.pop(_get_conn, None)

    return _override()


@pytest.mark.asyncio
async def test_http_dashboard_panels_load_on_legacy_schema() -> None:
    """HTTP panels return 200 with degraded states, never a 500 retry loop."""
    conn = _legacy_conn()
    with _override_conn(conn):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            stages = await client.get(
                "/api/dashboard/sleep/stages",
                params={"start": "2026-06-01", "end": "2026-06-02"},
            )
            caps = await client.get("/api/dashboard/capabilities")

    assert stages.status_code == 200
    assert stages.json()["stage_data_available"] is False
    assert caps.status_code == 200
    caps_by_name = {item["name"]: item for item in caps.json()["capabilities"]}
    assert caps_by_name["steps"]["state"] == "available"
    assert caps_by_name["sleep"]["state"] == "malformed"
