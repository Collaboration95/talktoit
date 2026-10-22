"""Tiny generated-corpus acceptance for the slow runner's real entry points."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from app.bench import synthetic
from app.bench.corpus import CorpusSpec, verify_database, write_corpus
from app.bench.report import CaseReport
from app.bench.synthetic import run_case
from app.bench.workload import explain_workout_joins


def test_official_cli_http_queries_and_publication_are_synthetic(tmp_path, monkeypatch):
    spec = CorpusSpec("small", records=24, workouts=6, days=3, seed=137)
    imports = []
    requests = []
    real_measure = synthetic.measure_process

    def record_process(command, *, env, **kwargs):
        is_import = "app.ingest.run" in command
        if not is_import:
            assert not Path(env["TTI_APP_STATE_PATH"]).exists()
            requests.append(dict(env))
        result = real_measure(command, env=env, **kwargs)
        if is_import:
            imports.append(json.loads(result.stdout.splitlines()[-1]))
            # A stale legacy DB must never be mistaken for the managed generation.
            with duckdb.connect(env["TTI_DB_PATH"]) as decoy:
                decoy.execute("CREATE TABLE legacy_decoy (id INTEGER)")
            index = len(imports) - 1
            result = replace(
                result,
                elapsed_ms=[9999, 30, 60][index],
                peak_rss_bytes=[9999, 300, 600][index],
                memory_samples=[99, 2, 3][index],
            )
        else:
            body = json.loads(result.stdout.splitlines()[-1])
            for name in body["metrics"]:
                if name != "profile_calls":
                    body["metrics"][name] = [9999, 10, 20, 30][len(requests) - 1]
            result = replace(result, stdout=json.dumps(body))
        return result

    monkeypatch.setattr(synthetic, "measure_process", record_process)
    report = run_case(
        tmp_path,
        spec,
        workers=2,
        ingestion_warmups=1,
        ingestion_samples=2,
        warmups=1,
        samples=3,
        timeout=90,
    )
    assert len(imports) == 3
    assert len(requests) == 4
    assert len({item["TTI_APP_STATE_PATH"] for item in requests}) == 4
    assert len({item["TTI_DB_PATH"] for item in requests}) == 1
    assert {item["TTI_BENCH_GENERATION_ID"] for item in requests} == {
        imports[-1]["dataset_version_id"]
    }
    assert report.ingestion_sampling.samples == 2
    assert report.workload_sampling.samples == 3
    assert report.cold_cache_isolated
    assert report.managed_generation_verified
    metrics = {metric.name: metric for metric in report.measurements}
    assert metrics["ingest_full_wall"].summary.median == 45
    assert metrics["ingest_full_wall"].summary.p95 == 60
    assert metrics["ingest_tree_peak_rss"].summary.median == 450
    assert metrics["ingest_tree_peak_rss"].summary.p95 == 600
    assert metrics["chat_http_cold"].summary.median == 20
    assert metrics["chat_http_cold"].summary.p95 == 30
    assert metrics["workload_process_wall"].group == "workload"
    assert metrics["workload_process_wall"].summary.samples == 3
    assert report.memory_samples == 5
    invalid = report.model_dump()
    invalid["workload_sampling"]["samples"] = 20
    with pytest.raises(ValidationError):
        CaseReport.model_validate(invalid)
    assert report.parity_verified
    assert report.counts["records"] == 24
    assert report.counts["workout_statistics"] == 18
    assert report.provider_network_calls == 0
    assert report.provider_mode == "denied_stub"
    assert (
        next(
            metric for metric in report.measurements if metric.name == "profile_calls"
        ).summary.median
        == 4
    )
    names = {metric.name for metric in report.measurements}
    assert {
        "ingest_full_wall",
        "ingest_tree_peak_rss",
        "chat_http_cold",
        "chat_http_fresh",
        "chat_http_cached",
        "query_latest_cold",
        "query_latest_warm",
        "query_ranked_warm",
        "query_paged_warm",
    } <= names
    assert all(
        metric.summary.samples == (2 if metric.group == "ingestion" else 3)
        for metric in report.measurements
    )
    assert report.dashboard_requests == dict.fromkeys(
        (
            "summary",
            "workouts",
            "volume",
            "steps",
            "heart",
            "sleep",
            "sleep_stages",
            "capabilities",
            "status",
        ),
        1,
    )
    assert set(report.explain_analyze) == {"latest", "ranked", "paged"}
    assert all(report.explain_analyze.values())
    published = report.model_dump_json()
    for secret in (
        str(tmp_path),
        "show my last",
        "SELECT ",
        "HealthData",
        "HKQuantityType",
        "sourceName",
        "duration_minutes",
        "source_path",
    ):
        assert secret not in published
    assert json.loads(published)["browser_evidence"] == "unavailable_requires_browser_run"


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_counts_values_relations_and_real_explain_analyze(tmp_path, workers):
    from app.ingest.coordinator import ingest_v2

    source = tmp_path / "synthetic.xml"
    spec = CorpusSpec("small", records=24, workouts=6, days=3, seed=137)
    corpus = write_corpus(source, spec)
    with duckdb.connect(":memory:") as conn:
        ingest_v2(source, conn, n_workers=workers)
        verify_database(conn, spec, corpus)
        plans = explain_workout_joins(conn)
        assert set(plans) == {"latest", "ranked", "paged"}
        assert all("EXPLAIN_ANALYZE" in plan or "QUERY" in plan for plan in plans.values())
        conn.execute("DELETE FROM workout_metadata")
        try:
            verify_database(conn, spec, corpus)
        except RuntimeError as error:
            assert str(error) == "synthetic_parity_failed"
        else:
            raise AssertionError("broken child counts must reject the run")
