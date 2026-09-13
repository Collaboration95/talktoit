"""Workout route files resolve against the export root recorded at import time.

Apple exports store route references as root-relative paths such as
/workout-routes/route.gpx. The import records the export directory it read, and
the workout-detail handler must resolve route files inside that directory
instead of assuming an environment variable that normal imports never set.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from httpx import ASGITransport, AsyncClient

from app.ingest.coordinator import ingest_v2
from app.main import app
from app.state.app_state import AppStateRepository

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPORT_XML = FIXTURES / "sample.xml"
GPX_FIXTURE = FIXTURES / "route.gpx"

ROUTE_NAMES = ("route_2026-06-05_7.00am.gpx", "route_2026-06-08_6.00pm.gpx")


def _materialize_export(tmp_path: Path) -> Path:
    """Build an export directory containing the XML and its referenced routes."""
    export_dir = tmp_path / "apple_health_export"
    route_dir = export_dir / "workout-routes"
    route_dir.mkdir(parents=True)
    shutil.copy(EXPORT_XML, export_dir / "export.xml")
    for name in ROUTE_NAMES:
        shutil.copy(GPX_FIXTURE, route_dir / name)
    return export_dir


@pytest.mark.asyncio
async def test_workout_detail_resolves_route_from_recorded_export_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real import root makes the stored route renderable at the HTTP boundary."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    export_dir = _materialize_export(tmp_path)

    db = duckdb.connect(":memory:")
    try:
        ingest_v2(str(export_dir / "export.xml"), db)
        AppStateRepository().activate_file(
            export_dir / "export.xml",
            parser_version="v2",
            schema_version="1",
            worker_count=1,
            coverage_start=None,
            coverage_end=None,
            counts={},
            warnings=(),
            export_root=str(export_dir),
        )

        from app.api.dashboard import _get_conn

        def override() -> Generator[duckdb.DuckDBPyConnection, None, None]:
            yield db

        app.dependency_overrides[_get_conn] = override
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/dashboard/workouts/1")
        finally:
            app.dependency_overrides.pop(_get_conn, None)
    finally:
        db.close()

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["state"] == "available"
    assert body["gps_route"] is not None
    assert len(body["gps_route"]["coordinates"]) == 3


def test_resolve_export_root_prefers_the_recorded_import_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorded root wins over the environment and database-directory fallbacks."""
    from app.api.dashboard import _resolve_export_root

    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_EXPORT_PATH", str(tmp_path / "unrelated"))
    export_dir = _materialize_export(tmp_path)
    repo = AppStateRepository()
    repo.activate_file(
        export_dir / "export.xml",
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start=None,
        coverage_end=None,
        counts={},
        warnings=(),
        export_root=str(export_dir),
    )

    assert _resolve_export_root(repo) == export_dir.resolve()
