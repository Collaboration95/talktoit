"""Tiny generated-corpus acceptance for the slow runner's real entry points."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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
    real_verify = synthetic.verify_database

    def verify_with_lease(conn, recipe, corpus):
        from app.db.connection import snapshot_for_connection

        snapshot = snapshot_for_connection(conn)
        assert snapshot is not None
        assert snapshot.dataset is not None
        assert snapshot.dataset.worker_count == 2
        real_verify(conn, recipe, corpus)

    monkeypatch.setattr(synthetic, "verify_database", verify_with_lease)

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
    assert [item["TTI_BENCH_PLAN_MATRIX"] for item in requests] == ["0", "1", "0", "0"]
    assert report.plan_matrix_runs == 1
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
    from app.bench.report import PLAN_VARIANTS

    assert set(report.plan_variants) == set(PLAN_VARIANTS)
    assert all(item.success for item in report.plan_variants.values())
    assert all(item.operator_cardinality is None for item in report.plan_variants.values())
    unsafe = report.model_dump()
    unsafe["plan_variants"]["PRIVATE /query"] = {"success": True, "result_rows": 1}
    with pytest.raises(ValidationError):
        CaseReport.model_validate(unsafe)
    incomplete = report.model_dump()
    del incomplete["plan_variants"]["paged_source_next"]
    with pytest.raises(ValidationError):
        CaseReport.model_validate(incomplete)
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


async def test_workload_leases_fresh_state_retention_ownership_and_no_active(tmp_path, monkeypatch):
    from app.bench import workload
    from app.bench.synthetic import BACKEND, isolated_environment
    from app.db.connection import dataset_snapshot, delete_health_database
    from app.db.dataset_lifecycle import DatasetLifecycle
    from app.llm.cache_keys import CACHE_KEY_VERSION
    from app.state.app_state import AppStateRepository

    assert CACHE_KEY_VERSION == "chat-cache-v6"
    env = isolated_environment(tmp_path)
    source = tmp_path / "synthetic.xml"
    ids = []
    for seed in (137, 271):
        write_corpus(source, CorpusSpec("small", records=24, workouts=6, days=3, seed=seed))
        result = synthetic.measure_process(
            [
                sys.executable,
                "-m",
                "app.ingest.run",
                str(source),
                "--workers",
                "1",
                "--report-json",
            ],
            cwd=BACKEND,
            env=env,
            timeout=90,
        )
        ids.append(json.loads(result.stdout.splitlines()[-1])["dataset_version_id"])
    env["TTI_BENCH_GENERATION_ID"] = ids[-1]
    lifecycle = DatasetLifecycle(Path(env["TTI_DB_PATH"]))

    def inventory():
        # Read-only digests of this tiny test's owned store; no protocol is rewritten.
        records = {
            str(path.relative_to(lifecycle.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in lifecycle.root.rglob("*.json")
        }
        locks = {
            str(path.relative_to(lifecycle.root)): (path.stat().st_dev, path.stat().st_ino)
            for path in lifecycle.root.rglob("*.lock")
        }
        with lifecycle.writer_lock():
            protected = lifecycle.protected_generation_ids()
        return records, locks, protected

    with patch.dict(os.environ, env, clear=True):
        before = inventory()
        assert before[2] == frozenset(ids)
        assert len([name for name in before[0] if name.endswith("record.json")]) == 2
        leased = []

        @contextmanager
        def counted_snapshot(*args, **kwargs):
            with dataset_snapshot(*args, **kwargs) as snapshot:
                assert snapshot.dataset.id == ids[-1]
                assert lifecycle.generation_is_leased(ids[-1])
                leased.append(snapshot.dataset.id)
                yield snapshot

        with monkeypatch.context() as scoped:
            scoped.setattr(workload, "dataset_snapshot", counted_snapshot, raising=False)
            metrics, plans, variants = workload.run_queries()
            assert (
                metrics and all(plans.values()) and all(item.success for item in variants.values())
            )
            assert len(leased) == 5  # Four new query connections, then EXPLAIN.
        for trial in range(2):
            fresh = tmp_path / f"fresh-{trial}"
            fresh.mkdir()
            fresh_env = isolated_environment(fresh)
            fresh_env["TTI_DB_PATH"] = env["TTI_DB_PATH"]
            fresh_env["TTI_BENCH_GENERATION_ID"] = ids[-1]
            with patch.dict(os.environ, fresh_env, clear=True):
                metrics, counts, network_calls = await workload.run_http()
                assert metrics["profile_calls"] == 4
                assert len(counts) == 9 and network_calls == 0
            assert inventory() == before
        delete_health_database(AppStateRepository())
        with dataset_snapshot() as empty:
            assert empty.dataset is None
            assert empty.database_path is None
        with pytest.raises(RuntimeError, match="synthetic_generation_mismatch"):
            workload.run_queries()
        fresh = tmp_path / "after-deletion"
        fresh.mkdir()
        fresh_env = isolated_environment(fresh)
        fresh_env["TTI_DB_PATH"] = env["TTI_DB_PATH"]
        fresh_env["TTI_BENCH_GENERATION_ID"] = ids[-1]
        with patch.dict(os.environ, fresh_env, clear=True):
            with pytest.raises(RuntimeError, match="synthetic_generation_mismatch"):
                await workload.run_http()
        assert lifecycle.active() is None
