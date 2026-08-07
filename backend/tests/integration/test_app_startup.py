"""Startup-telemetry contract tests.

The lifespan records an ``app``/``startup`` diagnostics event whose metadata is
allowlisted. The ``app_state_version`` field must report the schema version the
store actually migrates to — a hardcoded literal here is exactly how the stale
``"7"`` escaped (see AUDIT A-13 / GH-12). These tests pin that contract so the
field cannot drift on the next migration.
"""

from __future__ import annotations

from app.main import create_app
from app.state.app_state import APP_STATE_SCHEMA_VERSION, AppStateRepository
from app.state.diagnostics import DiagnosticsRepository


async def _startup_event_meta(monkeypatch, tmp_path) -> dict[str, str]:
    """Run the real lifespan once against an isolated app-state store."""
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
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
