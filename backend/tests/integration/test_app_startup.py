"""Startup-telemetry contract tests.

The lifespan records an ``app``/``startup`` diagnostics event whose metadata is
allowlisted. The ``app_state_version`` field must report the schema version the
store actually migrates to — a hardcoded literal here is exactly how the stale
``"7"`` escaped (see AUDIT A-13 / GH-12). These tests pin that contract so the
field cannot drift on the next migration.
"""

from __future__ import annotations

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.state.app_state import APP_STATE_SCHEMA_VERSION, AppStateRepository
from app.state.diagnostics import DiagnosticsRepository


async def _startup_event_meta(monkeypatch, tmp_path) -> dict[str, str]:
    """Run the real lifespan once against an isolated app-state store."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    # Keep contract tests hermetic: never spawn the owned LiteRT server here
    # (covered explicitly in tests/unit/test_litert_lifecycle.py).
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "0")
    app = create_app()
    async with app.router.lifespan_context(app):
        for event in DiagnosticsRepository().recent(limit=100, category="app"):
            if event.name == "startup":
                return dict(event.meta)
    raise AssertionError("lifespan did not record an app/startup diagnostics event")


async def test_startup_reports_current_app_state_schema_version(monkeypatch, tmp_path) -> None:
    """The startup event's app_state_version equals the store's applied version."""
    meta = await _startup_event_meta(monkeypatch, tmp_path)

    repo = AppStateRepository(tmp_path / "state.sqlite")
    assert meta["app_state_version"] == str(repo.schema_version())
    assert meta["app_state_version"] == str(APP_STATE_SCHEMA_VERSION)


async def test_startup_event_fields_are_allowlisted(monkeypatch, tmp_path) -> None:
    """The startup event stays inside the diagnostics privacy allowlist."""
    meta = await _startup_event_meta(monkeypatch, tmp_path)

    assert set(meta) == {"app_version", "duckdb_version", "schema_version", "app_state_version"}
    assert meta["app_version"]  # non-empty


async def test_exact_api_paths_return_json_not_spa_html() -> None:
    """Unknown /api paths must not fall through to the SPA catch-all."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api", "/api/", "/api/unknown-route"):
            response = await client.get(path)
            assert response.status_code == 404, path
            assert response.headers["content-type"].startswith("application/json"), path
            assert response.json() == {"detail": "API route not found"}, path


def test_runtime_version_tracks_backend_package_metadata() -> None:
    """APP_VERSION must come from the backend distribution, not a silent fallback."""
    from app.main import _DISTRIBUTION_NAME, APP_VERSION

    assert _DISTRIBUTION_NAME == "tti-backend"
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    declared = next(
        line.split('"')[1]
        for line in pyproject.read_text().splitlines()
        if line.startswith("version = ")
    )
    assert APP_VERSION == declared
