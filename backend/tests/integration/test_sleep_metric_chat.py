"""Synthetic acceptance of shared sleep coverage and explicit metric comparisons."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import duckdb
import pytest

from app.analytics.registry import execute_comparison
from app.api.dashboard import get_sleep, get_sleep_stages
from app.db import queries
from app.db.data_profile import DataProfile
from app.db.schema import SQL_CREATE_TABLES
from app.llm.local_planner import plan_local_question
from app.llm.orchestrator import ChatOrchestrator
from app.llm.provider_projection import narration_projection, planning_projection
from app.llm.tools import dispatch_tool


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        SQL_CREATE_TABLES.replace("source_name   VARCHAR NOT NULL", "source_name   VARCHAR")
    )
    yield conn
    conn.close()


def record(db, metric, start, value=None, end=None, source="Watch", label=None):
    db.execute(
        """INSERT INTO records (id, type, source_name, start_date, end_date, value, text_value)
        VALUES ((SELECT COALESCE(MAX(id), 0)+1 FROM records), ?, ?, ?, ?, ?, ?)""",
        [metric, source, start, end or start, value, label],
    )


def profile(latest=date(2026, 6, 17)):
    return DataProfile(
        first_date=date(2026, 5, 1),
        latest_date=latest,
        workout_types=(),
        metrics=("Steps", "Sleep"),
    )


def comparison_args(ids=None):
    return {
        "this_start": "2026-06-01",
        "this_end": "2026-06-07",
        "last_start": "2026-05-25",
        "last_end": "2026-05-27",
        "this_label": "1\u20137 Jun 2026",
        "last_label": "25\u201327 May 2026",
        "metric_ids": ids or ["steps", "resting_hr", "hrv"],
    }


@pytest.mark.parametrize("granularity", ["day", "week", "month"])
def test_sleep_dashboard_tool_parity_and_category_semantics(db, granularity):
    metric = "HKCategoryTypeIdentifierSleepAnalysis"
    # Local June 1 21:30 -> June 2 00:00; awake and core nested in InBed.
    for start, end, label in [
        ("13:30", "16:00", "InBed"),
        ("14:00", "15:00", "AsleepCore"),
        ("15:00", "15:30", "Awake"),
    ]:
        record(db, metric, f"2026-06-01 {start}", end=f"2026-06-01 {end}", label=label)
    record(db, metric, "2026-06-02 14:00", end="2026-06-02 16:00", label="Asleep")
    for source in ["AutoSleep", None]:
        record(db, metric, "2026-06-03 00:00", end="2026-06-03 20:00", source=source)
    # Interval begins outside window: do not clip or include its overlap.
    record(db, metric, "2026-05-31 15:00", end="2026-06-01 14:00")
    dash = get_sleep(granularity, date(2026, 6, 1), date(2026, 6, 7), db, None)
    template, chat = dispatch_tool(
        "get_sleep_trend",
        {"start_date": "2026-06-01", "end_date": "2026-06-07", "granularity": granularity},
        db,
        "sleep",
    )
    assert template == "trend_chart"
    assert chat["series"] == [p.model_dump() for p in dash.series]
    assert sum(p["value"] or 0 for p in chat["series"]) == 4.5
    assert "coverage" in chat["title"].lower()
    if granularity == "day":
        assert [p["value"] for p in chat["series"]] == [2.5, 2, None, None, None, None, None]
    stages = get_sleep_stages(date(2026, 6, 1), date(2026, 6, 7), db, None)
    assert stages.total_asleep_hours == 3
    assert stages.stages_hours == {"core": 1}


def test_sleep_start_bucket_retains_whole_overnight_interval(db):
    record(
        db,
        "HKCategoryTypeIdentifierSleepAnalysis",
        "2026-05-31 15:00",
        end="2026-05-31 23:00",
        label="Asleep",
    )
    result = queries.get_sleep_trend(db, date(2026, 5, 31), date(2026, 5, 31), "day")
    assert result.series[0].value == 8


def test_comparison_means_sources_missing_zero_and_local_days(db):
    for day, values in [(1, [1000, 3000]), (2, [8000]), (3, [10000]), (4, [10000])]:
        for value in values:
            record(
                db,
                "HKQuantityTypeIdentifierStepCount",
                f"2026-06-{day:02} 00:00",
                value,
                source="Phone" if value == 1000 else "Watch",
            )
    for day, value in [(25, 4000), (26, 6000)]:
        record(db, "HKQuantityTypeIdentifierStepCount", f"2026-05-{day} 00:00", value)
    for value in [50, 70]:
        record(db, "HKQuantityTypeIdentifierRestingHeartRate", "2026-06-01 00:00", value)
    record(db, "HKQuantityTypeIdentifierRestingHeartRate", "2026-06-02 00:00", 90)
    record(db, "HKQuantityTypeIdentifierStepCount", "2026-06-05 00:00", None)
    rows = execute_comparison(db, comparison_args()).metrics
    assert rows[0].this_value == 8000
    assert rows[0].last_value == 5000
    assert rows[0].delta == 3000
    assert rows[0].unit == "steps/day"
    assert (rows[0].this_observed_days, rows[0].this_requested_days) == (4, 7)
    assert (rows[0].last_observed_days, rows[0].last_requested_days) == (2, 3)
    assert rows[0].value_basis == "observed_day_mean"
    assert rows[1].this_value == 70  # observation mean, not daily mean 75
    assert rows[1].last_value is None and rows[1].delta is None
    assert rows[1].direction == "flat"
    assert rows[2].this_value is None and rows[2].last_value is None
    assert all(r.direction_tone == "neutral" for r in rows)
    # 16:00 UTC is next local day, exactly June 1 midnight. True zero counts.
    record(db, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "2026-05-31 16:00", 0)
    record(db, "HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "2026-05-31 15:59", 200)
    hrv = execute_comparison(db, comparison_args(["hrv"])).metrics[0]
    assert hrv.this_value == 0 and hrv.this_observed_days == 1 and hrv.unit == "ms"
    assert hrv.last_value is None


@pytest.mark.parametrize(
    "patch",
    [
        {"metric_ids": ["sleep"]},
        {"metric_ids": []},
        {"this_end": "2026-05-31"},
        {"last_start": "2026-06-01"},
        {"this_start": None},
    ],
)
def test_comparison_rejects_invalid_tool_input(db, patch):
    with pytest.raises(ValueError):
        dispatch_tool("get_comparison", comparison_args() | patch, db, "compare")
    with pytest.raises(ValueError):
        execute_comparison(db, comparison_args() | patch)


@pytest.mark.parametrize(
    "question,ids,dates",
    [
        (
            "Compare my steps from 1\u20137 June 2026 with 8\u201314 June 2026.",
            ["steps"],
            ("2026-06-01", "2026-06-07", "2026-06-08", "2026-06-14"),
        ),
        (
            "Compare resting HR and HRV from 2026-06-01 to 2026-06-07 vs 2026-05-25 to 2026-05-31.",
            ["resting_hr", "hrv"],
            ("2026-06-01", "2026-06-07", "2026-05-25", "2026-05-31"),
        ),
        (
            "Compare steps, resting heart rate, and HRV "
            "between June 1\u20137 and May 25\u201331, 2026.",
            ["steps", "resting_hr", "hrv"],
            ("2026-06-01", "2026-06-07", "2026-05-25", "2026-05-31"),
        ),
    ],
)
def test_documented_comparisons_plan_locally(question, ids, dates):
    plan = plan_local_question(question, profile())
    assert plan["tool_name"] == "get_comparison"
    assert plan["arguments"]["metric_ids"] == ids
    assert (
        tuple(plan["arguments"][k] for k in ["this_start", "this_end", "last_start", "last_end"])
        == dates
    )


@pytest.mark.parametrize(
    "question",
    [
        "Compare steps this week",
        "Compare steps from June 1\u20137 with May 25\u201331",
        "Compare steps and blood pressure this month",
        "Compare active energy this month",
        "Compare steps from 2026-06-07 to 2026-06-01 vs 2026-05-25 to 2026-05-31",
        "Compare steps from 2026-02-30 to 2026-03-07 vs 2026-05-25 to 2026-05-31",
    ],
)
def test_ambiguous_or_unsupported_metrics_clarify_locally(question):
    plan = plan_local_question(question, profile())
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"


@pytest.mark.parametrize(
    "question,reason,empty_reason",
    [
        ("How can I improve my sleep?", "unsupported", "unsupported"),
        ("Why did I sleep badly?", "unsupported", "unsupported"),
        ("Show sleep", "clarification_needed", "clarification_needed"),
        ("How did I sleep last week?", "no_matching_data", "clarification_needed"),
        ("Show daily sleep from 2026-06-01 to 2026-06-07", "no_matching_data", "no_matching_data"),
    ],
)
async def test_sleep_never_calls_provider_even_unsupported_or_empty(
    db, question, reason, empty_reason
):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=AssertionError("provider denied"))
    for p, expected in [(profile(), reason), (profile(None), empty_reason)]:
        response = await ChatOrchestrator(client=client, conn=db).answer(question, data_profile=p)
        assert response.template_id == "fallback"
        assert response.data["reason"] == expected
    client.chat.completions.create.assert_not_called()


def test_sleep_relative_window_is_dataset_anchored():
    plan = plan_local_question("Show daily sleep last week", profile())
    assert plan["tool_name"] == "get_sleep_trend"
    assert plan["arguments"] == {
        "start_date": "2026-06-08",
        "end_date": "2026-06-14",
        "granularity": "day",
    }


def test_sleep_projection_boundary_denies_questions_and_results():
    with pytest.raises(ValueError):
        planning_projection("Why was I sleeping poorly?", "local")
    with pytest.raises(ValueError):
        narration_projection(
            "a trend", "get_sleep_trend", {"series": [], "raw_intervals": ["private"]}
        )
    with pytest.raises(ValueError):
        narration_projection("a trend", "get_trend", {"metric_label": "Sleep", "series": []})


def test_workout_narrative_formats_singapore_date():
    from app.llm.answer_facts import deterministic_narrative, narration_facts

    text = deterministic_narrative(
        "workout_card",
        narration_facts(
            "workout_card", {"activity_type": "Running", "date": "2026-06-04T23:00:00Z"}
        ),
    )
    assert "5 Jun 2026" in text and "2026-06-04" not in text


@pytest.mark.parametrize(
    "question",
    [
        "Compare steps from 2026-06-01 to 2026-06-07 vs 2026-05-25 to 2026-05-31 or June 2025",
        "Compare steps between June 1\u20137 and May 25\u201331, 2026 and December 2025",
        "Steps versus last week",
        "Show sleep between June 1\u20137 and May 25\u201331, 2026",
        "Show sleep from 2026-02-30 to 2026-03-07",
    ],
)
def test_extra_or_ambiguous_date_scopes_are_not_inferred(question):
    plan = plan_local_question(question, profile())
    assert plan["tool_name"] == "get_fallback_answer"
    assert plan["arguments"]["reason"] == "clarification_needed"


@pytest.mark.parametrize(
    "patch",
    [
        {"start_date": "2026-06-08", "end_date": "2026-06-07"},
        {"metric_id": "steps"},
        {"granularity": "year"},
    ],
)
def test_sleep_tool_rejects_unexpected_or_invalid_arguments(db, patch):
    with pytest.raises(ValueError):
        dispatch_tool(
            "get_sleep_trend",
            {"start_date": "2026-06-01", "end_date": "2026-06-07", "granularity": "day"} | patch,
            db,
            "sleep",
        )


@pytest.mark.parametrize(
    "question,template",
    [
        ("Show daily sleep from 2026-06-01 to 2026-06-10", "trend_chart"),
        (
            "Compare steps, resting HR, and HRV from 2026-06-01 to 2026-06-07 "
            "vs 2026-05-25 to 2026-05-31",
            "comparison",
        ),
        ("Why did I sleep badly?", "fallback"),
        ("Compare steps this week", "fallback"),
    ],
)
async def test_http_and_cli_share_synthetic_envelopes_without_providers(
    tmp_path, monkeypatch, question, template
):
    import shutil
    from pathlib import Path

    from httpx import ASGITransport, AsyncClient

    from app.api.chat import _get_gateway
    from app.cli import chat as cli
    from app.db.dataset_lifecycle import DatasetLifecycle
    from app.ingest.coordinator import ingest_v2
    from app.main import create_app
    from app.state.app_state import AppStateRepository

    path = tmp_path / "health.duckdb"
    monkeypatch.setenv("TTI_DB_PATH", str(path))
    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "state.sqlite"))
    with duckdb.connect(str(path)) as conn:
        ingest_v2(
            Path(__file__).resolve().parents[1] / "fixtures" / "sample.xml", conn, n_workers=1
        )
        record(
            conn,
            "HKCategoryTypeIdentifierSleepAnalysis",
            "2026-06-01 14:00",
            end="2026-06-01 16:30",
            label="Asleep",
        )
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "records",
                "record_metadata",
                "hrv_beats",
                "workouts",
                "workout_statistics",
                "workout_events",
                "workout_routes",
                "workout_metadata",
                "activity_summaries",
            )
        }
    repository = AppStateRepository()
    repository.migrate()
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample.xml"
    manifest = repository.build_file_manifest(
        fixture,
        parser_version="v2",
        schema_version="1",
        worker_count=1,
        coverage_start="2026-06-01",
        coverage_end="2026-06-10",
        counts=counts,
    )
    lifecycle = DatasetLifecycle(path)
    with lifecycle.writer_lock():
        staging = lifecycle.new_staging()
        shutil.copyfile(path, staging)
        lifecycle.activate(staging, manifest, fixture.parent, repository)
    gateway = MagicMock(client=MagicMock(), model="denied")
    gateway.complete = AsyncMock(side_effect=AssertionError("provider denied"))
    monkeypatch.setattr(cli, "_ensure_local_server", lambda _: None)
    monkeypatch.setattr(cli, "get_gateway_for_config", lambda _: gateway)
    app = create_app()
    app.dependency_overrides[_get_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.post("/api/chat", json={"question": question, "cache_mode": "fresh"})
        if template == "trend_chart":
            first_conversation = repository.create_conversation("Sleep", manifest.id)
            current = await client.post(
                "/api/chat", json={"question": question, "conversation_id": first_conversation}
            )
            assert current.json()["template_id"] == "trend_chart"
            second_conversation = repository.create_conversation("Empty sleep", manifest.id)
            missing = await client.post(
                "/api/chat",
                json={
                    "question": "Show daily sleep from 2025-01-01 to 2025-01-07",
                    "conversation_id": second_conversation,
                },
            )
            assert missing.status_code == 200
            assert missing.json()["template_id"] == "fallback"
            assert missing.json()["data"]["reason"] == "no_matching_data"
    assert result.status_code == 200
    http = result.json()
    headless = await cli._ask_question(question, cache_mode="fresh")
    assert headless.template_id == http["template_id"] == template
    assert headless.data == http["data"]
    assert headless.narrative == http["narrative"]
    assert headless.metadata.provenance == http["metadata"]["provenance"]
    assert (
        headless.metadata.dataset_version_id
        == http["metadata"]["dataset_version_id"]
        == manifest.id
    )
    assert headless.metadata.coverage_start == http["metadata"]["coverage_start"] == "2026-06-01"
    assert headless.metadata.coverage_end == http["metadata"]["coverage_end"] == "2026-06-10"
    gateway.complete.assert_not_awaited()


def test_true_zero_comparison_is_an_observed_value_with_arithmetic_delta(db):
    record(db, "HKQuantityTypeIdentifierStepCount", "2026-05-25 00:00", 0)
    record(db, "HKQuantityTypeIdentifierStepCount", "2026-06-01 00:00", 100)
    row = execute_comparison(db, comparison_args(["steps"])).metrics[0]
    assert row.last_value == 0 and row.last_observed_days == 1
    assert row.this_value == 100 and row.delta == 100
    assert "percentage" not in row.model_dump()


def test_sleep_zero_duration_is_present_coverage_not_a_missing_bucket(db):
    record(db, "HKCategoryTypeIdentifierSleepAnalysis", "2026-06-01 14:00", label=None)
    result = queries.get_sleep_trend(db, date(2026, 6, 1), date(2026, 6, 2), "day")
    assert [point.value for point in result.series] == [0, None]


def test_comparison_projection_carries_rounded_coverage_facts_only():
    row = {
        "label": "HRV SDNN",
        "unit": "ms",
        "this_value": 35.51,
        "last_value": 25.123,
        "delta": 10.387,
        "direction": "up",
        "direction_tone": "neutral",
        "this_observed_days": 4,
        "this_requested_days": 7,
        "last_observed_days": 2,
        "last_requested_days": 3,
        "value_basis": "observation_mean",
        "raw_records": ["private"],
        "route": ["private"],
        "source_name": "private",
    }
    result = narration_projection("Compare HRV", "get_comparison", {"metrics": [row]})
    fact = result["facts"]["metrics"][0]
    assert fact["this_value"] == 36 and fact["last_value"] == 25 and fact["delta"] == 10
    assert fact["direction_tone"] == "neutral" and fact["this_observed_days"] == 4
    assert not {"raw_records", "route", "source_name"} & fact.keys()


@pytest.mark.parametrize(
    "question",
    [
        "How much REM did I get?",
        "How much REM did I get from 2026-06-01 to 2026-06-07",
        "Show my sleep stages from 2026-06-01 to 2026-06-07",
        "Show deep sleep last week",
        "Show core sleep last week",
        "How long was I asleep last week?",
        "Show awake time last week",
        "Show inbed time last week",
        "Show in-bed time last week",
        "Was I awake a lot last week?",
        "How long was I in bed last night?",
        "Explain my bedtime",
    ],
)
async def test_unsupported_sleep_category_wording_stays_local(db, question):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=AssertionError("provider denied"))
    response = await ChatOrchestrator(client=client, conn=db).answer(
        question, data_profile=profile()
    )
    assert response.template_id == "fallback"
    assert response.data["reason"] == "unsupported"
    assert "coverage" in response.data["text"]
    assert "not supported" in response.data["text"]
    client.chat.completions.create.assert_not_called()


def test_semantic_identity_includes_sleep_scope_and_comparison_metric_selection():
    from app.llm.semantic_candidates import plan_fingerprint

    sleep = {"start_date": "2026-06-01", "end_date": "2026-06-07", "granularity": "day"}
    fingerprint = plan_fingerprint("get_sleep_trend", sleep)
    assert fingerprint != plan_fingerprint("get_sleep_trend", sleep | {"start_date": "2025-06-01"})
    assert fingerprint != plan_fingerprint("get_sleep_trend", sleep | {"end_date": "2026-06-10"})
    assert fingerprint != plan_fingerprint("get_sleep_trend", sleep | {"granularity": "week"})
    steps = comparison_args(["steps"])
    assert plan_fingerprint("get_comparison", steps) != plan_fingerprint(
        "get_comparison", steps | {"metric_ids": ["resting_hr"]}
    )
    assert plan_fingerprint("get_comparison", steps) != plan_fingerprint(
        "get_comparison", steps | {"metric_ids": None}
    )
