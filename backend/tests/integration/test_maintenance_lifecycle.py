"""Synthetic CLI-to-readiness smoke for the supported macOS lifecycle job."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from httpx import ASGITransport, AsyncClient

from app import main
from app.db.connection import close_open_connections, connect
from app.llm import litert
from app.llm.provider_gateway import ProviderGateway
from app.state.app_state import AppStateRepository

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample.xml"
EXPECTED_COUNTS = {
    "records": 40,
    "record_metadata": 7,
    "hrv_beats": 7,
    "workouts": 3,
    "workout_events": 6,
    "workout_statistics": 8,
    "workout_routes": 2,
    "workout_metadata": 12,
    "activity_summaries": 5,
}


async def test_synthetic_cli_import_survives_app_restart(monkeypatch, tmp_path) -> None:
    """Import real fixture bytes, validate relations, and boot twice without a model."""
    db_path = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(db_path))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(tmp_path / "shards"))
    monkeypatch.setenv("TTI_INGEST_FALLBACK_LEGACY", "0")
    monkeypatch.setenv("TTI_LOCAL_AUTOSTART", "0")
    monkeypatch.setenv("TTI_LOCAL_STOP_ON_EXIT", "0")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("synthetic readiness must never use a provider")

    gateway = Mock(spec=ProviderGateway)
    gateway.aclose = AsyncMock()
    gateway.complete.side_effect = forbidden
    autostart = Mock(side_effect=forbidden)
    health_probe = Mock(side_effect=forbidden)
    monkeypatch.setattr(main, "make_provider_gateway", lambda: gateway)
    monkeypatch.setattr(litert, "ensure_running", autostart)
    monkeypatch.setattr(litert, "health", health_probe)

    # Exercise the real lifespan before import: readiness cannot claim a dataset.
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            response = await client.get("/api/status")
            assert response.status_code == 200
            assert response.json() == {"readiness": "no_active_import", "dataset": None}

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.ingest.run", str(FIXTURE), "--workers", "2", "--report-json"],
        cwd=FIXTURE.parents[2],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["mode"] == "v2"
    assert report["resolved_workers"] == 2
    assert {name: report["counts"][name] for name in EXPECTED_COUNTS} == EXPECTED_COUNTS
    manifest = AppStateRepository().get_active()
    assert manifest is not None
    assert manifest.id == report["dataset_version_id"]
    assert manifest.parser_version == "v2"

    with connect(read_only=True) as conn:
        for table, count in EXPECTED_COUNTS.items():
            # Identifiers are closed fixture constants, never user input.
            count_sql = f"SELECT count(*) FROM {table}"  # noqa: S608
            assert conn.execute(count_sql).fetchone() == (count,)
        for child, parent, key in (
            ("record_metadata", "records", "record_id"),
            ("hrv_beats", "records", "record_id"),
            ("workout_events", "workouts", "workout_id"),
            ("workout_statistics", "workouts", "workout_id"),
            ("workout_routes", "workouts", "workout_id"),
            ("workout_metadata", "workouts", "workout_id"),
        ):
            # The table/key tuple above is a closed fixture whitelist.
            relation_sql = (
                f"SELECT count(*) FROM {child} c LEFT JOIN {parent} p "  # noqa: S608
                f"ON c.{key} = p.id WHERE p.id IS NULL"
            )
            assert conn.execute(relation_sql).fetchone() == (0,)
        assert conn.execute(
            "SELECT duration FROM workouts WHERE activity_type = 'Running'"
        ).fetchone() == (45.5,)
        assert conn.execute(
            "SELECT sum(value) FROM records WHERE type = 'HKQuantityTypeIdentifierStepCount'"
        ).fetchone() == (90954.0,)

    app = main.create_app()
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
                response = await client.get("/api/status")
                assert response.status_code == 200
                body = response.json()
                assert body["readiness"] == "ready"
                assert body["dataset"]["id"] == manifest.id
                assert body["dataset"]["counts"]["records"] == 40
                assert body["dataset"]["coverage_end"] == report["coverage_end"]
                assert "source_path" not in body["dataset"]
    finally:
        close_open_connections(db_path)
    gateway.complete.assert_not_called()
    autostart.assert_not_called()
    health_probe.assert_not_called()
    assert gateway.aclose.await_count == 2
