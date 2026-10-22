"""Official-import HTTP/CLI, hosted mock boundary and durable v7 replay oracles."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import _get_gateway
from app.cli import chat as cli
from app.db.connection import dataset_snapshot
from app.llm import cache_keys
from app.llm.provider_gateway import ProviderUnavailableError
from app.llm.provider_projection import narration_projection, planning_projection
from app.llm.tools import dispatch_tool
from app.main import create_app
from app.models.chat import ChatResponse
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import _child


@pytest.fixture
def imported(tmp_path, monkeypatch):
    for key, value in {
        "TTI_DB_PATH": tmp_path / "health.duckdb",
        "TTI_APP_STATE_PATH": tmp_path / "state.sqlite",
        "TTI_INGEST_SHARDS": tmp_path / "shards",
    }.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.delenv("TTI_DISABLE_SEMANTIC_CANDIDATES", raising=False)
    export = tmp_path / "export.xml"
    rows = []
    for start, end, label in [
        ("2026-06-01 21:30", "2026-06-02 00:30", "InBed"),
        ("2026-06-01 22:00", "2026-06-01 23:00", "AsleepCore"),
        ("2026-06-01 23:00", "2026-06-01 23:30", "AsleepREM"),
        ("2026-06-15 22:00", "2026-06-16 00:00", "Asleep"),
        ("2026-07-01 22:00", "2026-07-02 02:00", "Asleep"),
    ]:
        rows.append(
            '<Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Synthetic" '
            f'startDate="{start}:00 +0800" endDate="{end}:00 +0800" '
            f'value="HKCategoryValueSleepAnalysis{label}"/>'
        )
    export.write_text('<HealthData locale="en_SG">' + "".join(rows) + "</HealthData>")
    _child(tmp_path, "import", export)
    repo = AppStateRepository()
    active = repo.get_active()
    assert active is not None and active.counts["records"] == 5
    config = repo.set_provider_config(
        {
            "provider": "groq",
            "mode": "remote_planning_and_narration",
        }
    )
    assert config["provider"] == "groq" and config["mode"] == "remote_planning_and_narration"
    gateway = MagicMock(client=MagicMock(), model="synthetic-hosted-collector")
    gateway.complete = AsyncMock(side_effect=ProviderUnavailableError("mock collector only"))
    gateway.client.chat.completions.create = AsyncMock(
        side_effect=AssertionError("transport denied")
    )
    monkeypatch.setattr(cli, "_ensure_local_server", lambda _: None)
    monkeypatch.setattr(cli, "get_gateway_for_config", lambda _: gateway)
    app = create_app()
    app.dependency_overrides[_get_gateway] = lambda: gateway
    yield app, repo, active, gateway
    app.dependency_overrides.clear()


async def ask_both(app, question, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"question": question, **kwargs})
    assert result.status_code == 200
    http = ChatResponse.model_validate(result.json())
    headless = await cli._ask_question(question, **kwargs)
    assert http.template_id == headless.template_id
    assert http.data == headless.data
    assert http.narrative == headless.narrative
    assert http.metadata.dataset_version_id == headless.metadata.dataset_version_id
    assert http.metadata.coverage_start == headless.metadata.coverage_start == "2026-06-01"
    assert http.metadata.coverage_end == headless.metadata.coverage_end == "2026-07-01"
    return http, headless


def assert_no_provider_calls(gateway):
    assert [call.args[0] for call in gateway.complete.call_args_list] == []
    gateway.complete.assert_not_called()
    gateway.client.chat.completions.create.assert_not_called()


async def test_hosted_collector_is_live_for_unrecognized_non_sleep_question(imported):
    app, _repo, _active, gateway = imported
    for response in await ask_both(app, "Explain my training patterns", cache_mode="fresh"):
        assert response.template_id == "fallback"
        assert response.data["reason"] == "provider_unavailable"
    assert [call.args[0] for call in gateway.complete.call_args_list] == ["planning", "planning"]
    gateway.client.chat.completions.create.assert_not_called()


@pytest.mark.parametrize(
    "alias",
    [
        "NREM",
        "non-REM",
        "nonrapid-eye-movement",
        "rapid eye movement",
        "rapid-eye-movement",
        "REM",
        "stages",
        "categories",
    ],
)
@pytest.mark.parametrize("sleep", ["", " sleep"])
async def test_stage_requests_never_reach_hosted_planning_or_narration(imported, alias, sleep):
    app, _repo, _active, gateway = imported
    question = f"Show {alias}{sleep} in June 2026"
    for response in await ask_both(app, question, cache_mode="fresh"):
        assert response.template_id == "fallback"
        assert response.data["reason"] == "unsupported"
        assert response.data["question"] == question
        assert "coverage" in response.data["text"]
        assert "Show daily sleep last week" in response.data["text"]
    assert_no_provider_calls(gateway)
    with pytest.raises(ValueError, match="remain local"):
        planning_projection(question, "synthetic metadata")
    with pytest.raises(ValueError, match="remain local"):
        narration_projection(question, "get_trend", {"metric_label": "Steps"})


@pytest.mark.parametrize(
    "fragment",
    [
        "on 1 June 2026",
        "1\u20137 June 2026",
        "1st June 2026",
        "Monday June 2026",
        "on 2026-06-01 in June 2026",
        "1 from 2026-06-01 to 2026-06-07",
    ],
)
async def test_unsupported_leading_date_fragment_clarifies_after_official_import(
    imported, fragment
):
    app, _repo, _active, gateway = imported
    for response in await ask_both(app, f"Show daily sleep {fragment}", cache_mode="fresh"):
        assert response.template_id == "fallback"
        assert response.data["reason"] == "clarification_needed"
        assert "date range" in response.data["text"]
    assert_no_provider_calls(gateway)


async def test_supported_week_month_and_stage_oracles_retain_their_scope(imported):
    app, _repo, _active, gateway = imported
    for clause, expected in [
        ("from 2026-06-01 to 2026-06-07", [("2026-06-01", 3)]),
        ("from 1\u20137 June 2026", [("2026-06-01", 3)]),
        ("in June 2026", [("2026-06-01", 3), ("2026-06-15", 2)]),
    ]:
        for response in await ask_both(app, f"Show daily sleep {clause}", cache_mode="fresh"):
            assert response.template_id == "trend_chart"
            assert [
                (p["bucket"], p["value"]) for p in response.data["series"] if p["value"] is not None
            ] == expected
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/dashboard/sleep/stages?start=2026-06-01&end=2026-06-07")
    assert result.status_code == 200
    assert result.json()["total_asleep_hours"] == 1.5
    assert result.json()["stages_hours"] == {"core": 1, "rem": 0.5}
    assert_no_provider_calls(gateway)


@pytest.mark.parametrize("cache_path", ["exact", "canonical", "semantic"])
@pytest.mark.parametrize(
    "question,reason",
    [
        ("Show daily sleep on 1 June 2026", "clarification_needed"),
        ("Show daily sleep 1\u20137 June 2026", "clarification_needed"),
        ("Show NREM sleep in June 2026", "unsupported"),
        ("Show rapid eye movement in June 2026", "unsupported"),
    ],
)
async def test_persisted_v7_wrong_scope_or_stage_cannot_replay(
    imported, monkeypatch, cache_path, question, reason
):
    app, repo, active, gateway = imported
    old_plan = {
        "tool_name": "get_sleep_trend",
        "arguments": {
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "granularity": "day",
        },
    }
    with dataset_snapshot() as snapshot:
        template, data = dispatch_tool(
            "get_sleep_trend", old_plan["arguments"], snapshot.connection, question
        )
    encoded = ChatResponse(
        template_id=template, data=data, narrative="Old wrong measurement"
    ).model_dump_json()
    identity = cache_keys.generation_identity(repo.get_provider_config())
    if cache_path == "semantic":
        conversation = repo.create_conversation("Retained v7 history", active.id)
        old_turn_id = repo.add_completed_turn(
            conversation, question, encoded, "default", "miss", cache_keys.snapshot_plan(old_plan)
        )
    else:
        with monkeypatch.context() as legacy:
            legacy.setattr(cache_keys, "CACHE_KEY_VERSION", "chat-cache-v7")
            key = cache_keys.build_cache_key(
                cache_path,
                question if cache_path == "exact" else old_plan,
                generation_identity=identity,
            )
        repo.put_cached_response(key, active.id, encoded, canonical_plan=old_plan)
        assert AppStateRepository().get_cached_response(key, active.id) == encoded
        current_key = cache_keys.build_cache_key(
            cache_path,
            question if cache_path == "exact" else old_plan,
            generation_identity=identity,
        )
        assert current_key != key
        assert AppStateRepository().get_cached_response(current_key, active.id) is None
    restarted = create_app()
    restarted.dependency_overrides[_get_gateway] = app.dependency_overrides[_get_gateway]
    for response in await ask_both(restarted, question):
        assert response.template_id == "fallback"
        assert response.data["reason"] == reason
        assert response.metadata.provenance not in {"cached", "semantic_cached"}
        assert response.metadata.dataset_version_id == active.id
    if cache_path == "semantic":
        assert AppStateRepository().get_turn(old_turn_id)["response_json"] == encoded
        assert json.loads(encoded)["template_id"] == "trend_chart"
    assert_no_provider_calls(gateway)
