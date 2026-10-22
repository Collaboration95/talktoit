"""Official synthetic imports for final #193/#170 review regressions."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.chat import _get_gateway
from app.cli import chat as cli
from app.db.connection import dataset_snapshot
from app.llm import cache_keys
from app.llm.tools import dispatch_tool
from app.main import create_app
from app.models.chat import ChatResponse
from app.state.app_state import AppStateRepository
from tests.integration.test_dataset_crash_recovery import _child


@pytest.fixture
def imported(tmp_path, monkeypatch, request):
    step_value = getattr(request, "param", "missing")
    monkeypatch.setenv("TTI_DB_PATH", str(tmp_path / "health.duckdb"))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(tmp_path / "shards"))
    monkeypatch.setenv("TTI_PROVIDER", "groq")
    monkeypatch.setenv("TTI_PROVIDER_MODE", "remote_planning_and_narration")
    export = tmp_path / "export.xml"
    rows = []
    for kind, value in [
        ("StepCount", step_value),
        ("ActiveEnergyBurned", step_value),
        ("RestingHeartRate", step_value),
        ("HeartRateVariabilitySDNN", step_value),
        ("DistanceWalkingRunning", "missing"),
        ("DistanceCycling", "0"),
    ]:
        rows.append(
            f'<Record type="HKQuantityTypeIdentifier{kind}" sourceName="Synthetic" '
            'startDate="2026-06-01 12:00:00 +0800" endDate="2026-06-01 12:01:00 +0800" '
            f'value="{value}"/>'
        )
    for start, end, label in [
        ("2026-06-01 21:30", "2026-06-02 00:30", "InBed"),
        ("2026-06-01 22:00", "2026-06-01 23:00", "AsleepCore"),
        ("2026-06-01 23:00", "2026-06-01 23:30", "AsleepREM"),
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
    assert active is not None and active.counts["records"] == 10
    gateway = MagicMock(client=MagicMock(), model="denied")
    gateway.complete = AsyncMock(side_effect=AssertionError("provider denied"))
    gateway.client.chat.completions.create = AsyncMock(
        side_effect=AssertionError("provider denied")
    )
    monkeypatch.setattr(cli, "_ensure_local_server", lambda _: None)
    monkeypatch.setattr(cli, "get_gateway_for_config", lambda _: gateway)
    app = create_app()
    app.dependency_overrides[_get_gateway] = lambda: gateway
    yield app, repo, active
    gateway.complete.assert_not_awaited()
    gateway.client.chat.completions.create.assert_not_awaited()
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "imported,expected,numeric_count",
    [("missing", "malformed", 0), ("0", "available", 1)],
    indirect=["imported"],
)
async def test_imported_metric_states_distinguish_malformed_zero_and_category(
    imported, expected, numeric_count
):
    app, _repo, _active = imported
    with dataset_snapshot() as snapshot:
        numeric = snapshot.connection.execute(
            "SELECT COUNT(value) FROM records WHERE type = 'HKQuantityTypeIdentifierStepCount'"
        ).fetchone()[0]
        assert numeric == numeric_count
        assert snapshot.connection.execute(
            "SELECT COUNT(value), COUNT(text_value) FROM records "
            "WHERE type = 'HKCategoryTypeIdentifierSleepAnalysis'"
        ).fetchone() == (0, 4)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        settings = await client.get("/api/settings")
        dashboard = await client.get("/api/dashboard/capabilities")
        assert settings.status_code == dashboard.status_code == 200
        states = settings.json()["quality"]["metric_states"]
        flags = {flag["name"]: flag for flag in dashboard.json()["capabilities"]}
        for metric in ["steps", "active_energy", "resting_hr", "hrv"]:
            assert states[metric] == flags[metric]["state"] == expected
        assert states["distance"] == flags["distance"]["state"] == "available"
        assert states["sleep"] == flags["sleep"]["state"] == "available"
        if numeric:
            response = await client.post(
                "/api/chat", json={"question": "Show my steps trend this year"}
            )
            assert response.status_code == 200
            assert response.json()["template_id"] == "trend_chart"
            assert [
                p["value"] for p in response.json()["data"]["series"] if p["value"] is not None
            ] == [0]


@pytest.mark.parametrize(
    "question,reason",
    [
        ("Show daily sleep from June 2026 to July 2026", "clarification_needed"),
        ("Show daily sleep in June 2026 and last week", "clarification_needed"),
        ("Show my sleep stages from 2026-06-01 to 2026-06-07", "unsupported"),
        ("How much REM did I get from 2026-06-01 to 2026-06-07", "unsupported"),
    ],
)
async def test_imported_http_cli_reject_wrong_scope_or_measurement(imported, question, reason):
    app, _repo, _active = imported
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"question": question})
    assert result.status_code == 200
    http = result.json()
    headless = await cli._ask_question(question)
    assert http["template_id"] == headless.template_id == "fallback"
    assert http["data"] == headless.data
    assert headless.data["question"] == question
    assert headless.data["reason"] == reason
    assert headless.data["text"]


async def test_imported_sleep_coverage_and_stage_oracles_stay_distinct(imported):
    app, _repo, _active = imported
    question = "Show daily sleep from 2026-06-01 to 2026-07-31"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"question": question})
        stages = await client.get("/api/dashboard/sleep/stages?start=2026-06-01&end=2026-06-07")
    assert result.status_code == stages.status_code == 200
    assert result.json()["template_id"] == "trend_chart"
    assert [
        (p["bucket"], p["value"]) for p in result.json()["data"]["series"] if p["value"] is not None
    ] == [
        ("2026-06-01", 3),
        ("2026-07-01", 4),
    ]
    assert stages.json()["total_asleep_hours"] == 1.5
    assert stages.json()["stages_hours"] == {"core": 1, "rem": 0.5}
    headless = await cli._ask_question(question)
    assert headless.data == result.json()["data"]


@pytest.mark.parametrize("cache_path", ["exact", "canonical", "semantic"])
@pytest.mark.parametrize(
    "question,reason",
    [
        ("Show daily sleep from June 2026 to July 2026", "clarification_needed"),
        ("How much REM did I get from 2026-06-01 to 2026-06-07", "unsupported"),
    ],
)
async def test_persisted_v6_sleep_answers_cannot_bypass_new_planning(
    imported, monkeypatch, cache_path, question, reason
):
    app, repo, active = imported
    old_plan = {
        "tool_name": "get_sleep_trend",
        "arguments": {
            "start_date": "2026-06-01",
            "end_date": "2026-06-30" if reason == "clarification_needed" else "2026-06-07",
            "granularity": "day" if reason == "clarification_needed" else "week",
        },
    }
    with dataset_snapshot() as snapshot:
        template, data = dispatch_tool(
            "get_sleep_trend", old_plan["arguments"], snapshot.connection, question
        )
    encoded = ChatResponse(
        template_id=template, data=data, narrative="June coverage: 3 hours"
    ).model_dump_json()
    identity = cache_keys.generation_identity(repo.get_provider_config())
    if cache_path == "semantic":
        conversation = repo.create_conversation("Legacy sleep", active.id)
        old_turn_id = repo.add_completed_turn(
            conversation, question, encoded, "default", "miss", cache_keys.snapshot_plan(old_plan)
        )
    else:
        with monkeypatch.context() as legacy:
            legacy.setattr(cache_keys, "CACHE_KEY_VERSION", "chat-cache-v6")
            key = cache_keys.build_cache_key(
                cache_path,
                question if cache_path == "exact" else old_plan,
                generation_identity=identity,
            )
        repo.put_cached_response(key, active.id, encoded, canonical_plan=old_plan)
    # Reopen the repository/app to prove this is durable state, not a process cache.
    assert AppStateRepository().get_active().id == active.id
    restarted = create_app()
    restarted.dependency_overrides[_get_gateway] = app.dependency_overrides[_get_gateway]
    async with AsyncClient(
        transport=ASGITransport(app=restarted), base_url="http://test"
    ) as client:
        result = await client.post("/api/chat", json={"question": question})
    headless = await cli._ask_question(question)
    assert result.status_code == 200
    assert result.json()["template_id"] == headless.template_id == "fallback"
    assert result.json()["data"]["reason"] == headless.data["reason"] == reason
    assert result.json()["metadata"]["provenance"] not in {"cached", "semantic_cached"}
    assert headless.metadata.provenance not in {"cached", "semantic_cached"}
    if cache_path == "semantic":
        assert (
            json.loads(repo.get_turn(old_turn_id)["response_json"])["template_id"] == "trend_chart"
        )
