"""Daily-use readiness, privacy and fallback contracts; synthetic boundaries only."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.state.app_state import AppStateRepository


@pytest.fixture
def settings_client(monkeypatch, tmp_path):
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


@pytest.mark.parametrize("reachable,available", [(True, True), (True, False), (False, False)])
async def test_local_readiness_agrees(settings_client, monkeypatch, reachable, available):
    from app.llm import litert

    monkeypatch.setattr(
        litert, "status", lambda **kw: {"running": False, "binary_available": False}
    )

    def probe(**kw):
        assert kw["timeout_seconds"] == 1.0
        return {"ok": available, "endpoint_reachable": reachable, "model_available": available}

    monkeypatch.setattr(litert, "health", probe)
    async with settings_client as client:
        settings = (await client.get("/api/settings")).json()["provider"]
        health = (await client.get("/api/settings/llm/health")).json()
    assert settings["litert_status"] == health["status"]
    assert settings["litert_health"] == health["health"]
    assert health["status"]["available"] is available
    if reachable:
        assert health["status"]["ownership"] == "external"


@pytest.mark.parametrize(
    "error", [TimeoutError("secret /private/model"), RuntimeError("secret /private/model")]
)
async def test_probe_errors_are_safe(settings_client, monkeypatch, error):
    from app.llm import litert

    monkeypatch.setattr(litert, "status", lambda **kw: {"running": False})

    def probe(**kw):
        raise error

    monkeypatch.setattr(litert, "health", probe)
    async with settings_client as client:
        settings = (await client.get("/api/settings")).json()["provider"]
        health = (await client.get("/api/settings/llm/health")).json()
    assert settings["litert_health"] == health["health"]
    assert health["health"]["ok"] is False
    assert "secret" not in str(health)
    assert "/private" not in str(health)


async def test_nonloopback_is_rejected_before_status_or_http(settings_client, monkeypatch):
    from app.llm import litert

    repo = AppStateRepository()
    repo.set_provider_config({"provider": "local", "litert_base_url": "https://example.com/v1"})

    def forbidden(**kw):
        pytest.fail("nonloopback configuration must not probe")

    monkeypatch.setattr(litert, "status", forbidden)
    monkeypatch.setattr(litert, "health", forbidden)
    async with settings_client as client:
        settings = (await client.get("/api/settings")).json()["provider"]
        health = (await client.get("/api/settings/llm/health")).json()
    assert settings["litert_health"] == health["health"]
    assert health["health"]["ok"] is False
    assert "loopback" in health["health"]["error"]


async def test_slow_health_probe_leaves_event_loop_free(settings_client, monkeypatch):
    from app.llm import litert

    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(litert, "status", lambda **kw: {"running": False})

    def probe(**kw):
        entered.set()
        release.wait(2)
        return {"ok": False}

    monkeypatch.setattr(litert, "health", probe)
    async with settings_client as client:
        task = asyncio.create_task(client.get("/api/settings/llm/health"))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert (await asyncio.wait_for(client.get("/health"), 0.5)).status_code == 200
            assert not task.done()
        finally:
            release.set()
            await task


async def test_hosted_disclosure_matches_saved_mode_without_probe(settings_client, monkeypatch):
    from app.llm import litert

    def forbidden(**kw):
        pytest.fail("hosted settings must not probe providers")

    monkeypatch.setattr(litert, "health", forbidden)
    async with settings_client as client:
        for mode in ("remote_planning", "remote_planning_and_narration", "local_only"):
            saved = (
                await client.put("/api/settings/provider", json={"provider": "groq", "mode": mode})
            ).json()
            read = (await client.get("/api/settings")).json()["provider"]
            health = (await client.get("/api/settings/llm/health")).json()
            assert (
                saved["egress_categories"]
                == read["egress_categories"]
                == health["egress_categories"]
            )
            if mode == "local_only":
                assert saved["egress_categories"] == []
            else:
                assert "question text" in " ".join(saved["egress_categories"])
                assert "metadata" in " ".join(saved["egress_categories"])


@pytest.mark.parametrize(
    "question,reason",
    [
        ("Top 5 runs by pace", "unsupported"),
        ("Show my last workout", "no_matching_data"),
        ("Compare that", "clarification_needed"),
        ("What could this mysterious thing mean?", "provider_unavailable"),
    ],
)
async def test_fallback_reasons_stay_local_and_safe(question, reason):
    from datetime import date

    import duckdb

    from app.db.data_profile import DataProfile
    from app.db.schema import reset_schema
    from app.llm.orchestrator import ChatOrchestrator

    conn = duckdb.connect(":memory:")
    reset_schema(conn)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("secret SELECT raw"))
    profile = DataProfile(date(2026, 1, 1), date(2026, 1, 31), ("Running",), ("steps",))
    try:
        result = await ChatOrchestrator(client=client, conn=conn).answer(
            question, data_profile=profile
        )
        assert result.template_id == "fallback"
        assert result.data["reason"] == reason
        assert result.data["text"]
        assert "secret" not in str(result.data)
        if reason != "provider_unavailable":
            client.chat.completions.create.assert_not_awaited()
    finally:
        conn.close()


async def test_saved_effective_model_and_endpoint_are_probed(settings_client, monkeypatch):
    from app.llm import litert

    repo = AppStateRepository()
    repo.set_provider_config(
        {
            "provider": "local",
            "litert_model": "synthetic-model",
            "litert_base_url": "http://localhost:9401/v1",
        }
    )
    calls = []
    monkeypatch.setattr(litert, "status", lambda **kw: {"running": True})

    def probe(**kw):
        calls.append(kw)
        return {"ok": True, "endpoint_reachable": True, "model_available": True}

    monkeypatch.setattr(litert, "health", probe)
    async with settings_client as client:
        await client.get("/api/settings")
        await client.get("/api/settings/llm/health")
    assert (
        calls
        == [
            {
                "base_url": "http://localhost:9401/v1",
                "model": "synthetic-model",
                "timeout_seconds": 1.0,
            }
        ]
        * 2
    )


async def test_http_and_cli_json_keep_fallback_contract(
    settings_client, monkeypatch, tmp_path, capsys
):
    import json
    from pathlib import Path

    import duckdb

    from app.cli import chat
    from app.ingest.coordinator import ingest_v2
    from app.llm.orchestrator import ChatOrchestrator
    from app.models.chat import ChatResponse

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample.xml"
    conn = duckdb.connect(str(tmp_path / "health.duckdb"))
    ingest_v2(str(fixture), conn)
    conn.close()
    repo = AppStateRepository()
    repo.activate_file(
        fixture,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-06-01",
        coverage_end="2026-06-08",
        counts={"workouts": 3},
    )

    async def forbidden(*args, **kwargs):
        pytest.fail("supported fallback must not call a provider")

    monkeypatch.setattr(ChatOrchestrator, "_complete_provider", forbidden)
    async with settings_client as client:
        response = await client.post("/api/chat", json={"question": "Top 5 runs by pace"})
    assert response.status_code == 200
    validated = ChatResponse.model_validate(response.json())
    assert validated.data["reason"] == "unsupported"
    monkeypatch.setattr(chat, "_ensure_local_server", lambda config: None)
    cli_response = await chat._ask_question("Top 5 runs by pace", cache_mode="fresh")
    chat._print_response(cli_response, json_output=True)
    cli_json = json.loads(capsys.readouterr().out)
    assert ChatResponse.model_validate(cli_json).data["reason"] == "unsupported"
    assert cli_json["template_id"] == validated.template_id


@pytest.mark.parametrize(
    "question", ["Top 5 longest runs this year", "Show my steps trend this year"]
)
async def test_empty_measurements_offer_local_recovery(question):
    from datetime import date

    import duckdb

    from app.db.data_profile import DataProfile
    from app.db.schema import reset_schema
    from app.llm.orchestrator import ChatOrchestrator

    conn = duckdb.connect(":memory:")
    reset_schema(conn)
    client = MagicMock()
    profile = DataProfile(date(2026, 1, 1), date(2026, 1, 31), ("Running",), ("steps",))
    try:
        response = await ChatOrchestrator(client=client, conn=conn).answer(
            question, data_profile=profile
        )
        assert response.template_id == "fallback"
        assert response.data["reason"] == "no_matching_data"
        assert "date range" in response.data["text"]
        client.chat.completions.create.assert_not_called()
    finally:
        conn.close()
