"""Tiny generated-corpus acceptance for the slow runner's real entry points."""

from __future__ import annotations

import json

import duckdb
import pytest

from app.bench.corpus import CorpusSpec, verify_database, write_corpus
from app.bench.synthetic import run_case
from app.bench.workload import explain_workout_joins


def test_official_cli_http_queries_and_publication_are_synthetic(tmp_path):
    spec = CorpusSpec("small", records=24, workouts=6, days=3, seed=137)
    report = run_case(tmp_path, spec, workers=2, warmups=1, samples=2, timeout=90)
    assert report.parity_verified
    assert report.counts["records"] == 24
    assert report.counts["workout_statistics"] == 18
    assert report.provider_network_calls == 0
    assert report.provider_mode == "denied_stub"
    assert (
        next(
            metric for metric in report.measurements if metric.name == "profile_calls"
        ).summary.median
        == 3
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
    assert all(metric.summary.samples == 2 for metric in report.measurements)
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
