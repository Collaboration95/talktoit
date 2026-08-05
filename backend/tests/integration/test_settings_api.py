"""Settings API contracts: introspection, scoped clears, and health deletion."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
from httpx import ASGITransport, AsyncClient

from app.db.connection import resolve_db_path
from app.ingest.parser import ingest
from app.main import create_app
from app.state.app_state import AppStateRepository
from app.state.diagnostics import DiagnosticsRepository

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


def _client(monkeypatch, tmp_path) -> AsyncClient:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _activate_sample_dataset(monkeypatch, tmp_path) -> None:
    import duckdb

    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    path = tmp_path / "health.duckdb"
    conn = duckdb.connect(str(path))
    ingest(str(FIXTURE), conn)
    conn.close()
    AppStateRepository().activate(
        source_bytes=b"",
        source_size_bytes=0,
        parser_version="legacy-v1",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-01-01",
        coverage_end="2026-01-31",
        counts={"records": 1},
    )


async def test_settings_reports_provider_mode_and_storage(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        settings = (await client.get("/api/settings")).json()
    assert settings["provider"]["mode"] == "local_only"
    assert settings["provider"]["egress_categories"] == []
    assert "app_state_bytes" in settings["storage"]
    assert settings["storage"]["cache"] == {"entries": 0, "bytes": 0}
    assert settings["storage"]["conversations"] == 0
    assert settings["quality"]["vocabulary"] == [
        "available",
        "unavailable",
        "out_of_range",
        "unsupported",
        "malformed",
    ]


async def test_settings_lists_metric_availability_from_import(monkeypatch, tmp_path) -> None:
    _activate_sample_dataset(monkeypatch, tmp_path)
    async with _client(monkeypatch, tmp_path) as client:
        settings = (await client.get("/api/settings")).json()
    assert settings["dataset"] is not None
    states = settings["quality"]["metric_states"]
    assert "steps" in states
    assert states["steps"] in {"available", "out_of_range"}


async def test_scoped_clear_operations_are_independent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    repo = AppStateRepository()
    diagnostics = DiagnosticsRepository()
    repo.put_cached_response("k", "ds", json.dumps({"a": 1}))
    repo.create_conversation("Runs", "ds")
    diagnostics.record(
        "panel", "panel:steps", status="empty", meta={"panel_name": "steps", "state": "empty"}
    )

    async with _client(monkeypatch, tmp_path) as client:
        cleared_cache = await client.request(
            "DELETE",
            "/api/settings/cache",
            json={"confirm": True, "scope": "cache"},
        )
        assert cleared_cache.status_code == 200
        assert cleared_cache.json()["cleared"] == 1
        assert repo.cache_usage() == {"entries": 0, "bytes": 0}

        wrong = await client.request(
            "DELETE",
            "/api/settings/cache",
            json={"confirm": True, "scope": "wrong"},
        )
        assert wrong.status_code == 422

    assert repo.count_conversations() == 1  # history untouched by cache clear
    assert diagnostics.count() == 1  # diagnostics untouched

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        cleared_history = await client.request(
            "DELETE",
            "/api/settings/history",
            json={"confirm": True, "scope": "history"},
        )
        assert cleared_history.json()["deleted"] == 1

    assert repo.count_conversations() == 0


async def test_refuses_delete_without_confirmation(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        refused = await client.request(
            "DELETE",
            "/api/settings/health",
            json={"confirm": False, "scope": "health"},
        )
        assert refused.status_code == 422


async def test_delete_health_data_requires_health_scope_and_deactivates(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    repo = AppStateRepository()
    path = tmp_path / "health.duckdb"
    conn = duckdb.connect(str(path))
    ingest(str(FIXTURE), conn)
    conn.close()
    repo.activate(
        source_bytes=b"",
        source_size_bytes=0,
        parser_version="v2",
        schema_version="1",
        worker_count=2,
        coverage_start="2026-01-01",
        coverage_end="2026-01-31",
        counts={"records": 1},
    )

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        # Wrong scope must not delete health data.
        wrong = await client.request(
            "DELETE",
            "/api/settings/health",
            json={"confirm": True, "scope": "cache"},
        )
        assert wrong.status_code == 422
        assert resolve_db_path().exists()

        deleted = await client.request(
            "DELETE",
            "/api/settings/health",
            json={"confirm": True, "scope": "health"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 1
    assert not resolve_db_path().exists()
    assert repo.get_active() is None
