"""Functional harness regressions; no timing assertions or representative runs."""

from __future__ import annotations

import gzip
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.bench.corpus import CASES, CorpusSpec, write_corpus
from app.bench.process import measure_process, tree_rss_bytes
from app.bench.report import Measurement, summarize
from app.bench.synthetic import initial_js_bytes, isolated_environment


def test_summary_uses_all_samples_median_and_nearest_rank_p95():
    summary = summarize([100.0, 1.0, 2.0, 3.0, 4.0])
    assert summary.samples == 5
    assert summary.median == 3.0
    assert summary.p95 == 100.0
    assert summarize([4.0, 2.0]).median == 3.0
    assert summarize(list(map(float, range(1, 21)))).p95 == 19.0
    assert summarize([2.0]).p95 == 2.0


@pytest.mark.parametrize("samples", [[], [-1.0], [math.inf], [math.nan]])
def test_summary_rejects_invalid_samples(samples):
    with pytest.raises(ValueError):
        summarize(samples)


def test_fixed_cases_are_bounded_and_seed_reproducible(tmp_path):
    assert set(CASES) == {"small", "representative"}
    assert CASES["representative"].records > CASES["small"].records
    spec = CorpusSpec("small", records=24, workouts=6, days=3, seed=137)
    first = write_corpus(tmp_path / "first.xml", spec)
    second = write_corpus(tmp_path / "second.xml", spec)
    third = write_corpus(tmp_path / "third.xml", replace(spec, seed=271))
    assert first.sha256 == second.sha256 != third.sha256
    assert first.counts == {
        "records": 24,
        "record_metadata": 6,
        "hrv_beats": 0,
        "workouts": 6,
        "workout_events": 6,
        "workout_statistics": 18,
        "workout_routes": 0,
        "workout_metadata": 6,
        "activity_summaries": 3,
    }
    assert first.source_bytes == (tmp_path / "first.xml").stat().st_size
    with pytest.raises(ValueError):
        write_corpus(tmp_path / "bad.xml", replace(spec, records=-1))


def test_tree_peak_is_simultaneous_descendant_rss_in_bytes():
    snapshot = "10 1 100\n11 10 200\n12 11 50\n13 1 900\n"
    assert tree_rss_bytes(snapshot, 10) == 350 * 1024
    assert tree_rss_bytes(snapshot, 11) == 250 * 1024
    assert tree_rss_bytes(snapshot, 99) == 0
    with pytest.raises(ValueError):
        tree_rss_bytes("corrupt snapshot", 10)


def test_process_measurement_and_failure_do_not_publish_child_output(tmp_path):
    result = measure_process(
        [sys.executable, "-c", "import time; time.sleep(0.12)"],
        cwd=tmp_path,
        env=isolated_environment(tmp_path),
        interval=0.01,
        timeout=10,
    )
    assert result.elapsed_ms > 0
    assert result.peak_rss_bytes > 0
    assert result.memory_samples > 0
    with pytest.raises(RuntimeError, match="child_failed") as error:
        measure_process(
            [sys.executable, "-c", 'raise RuntimeError("PRIVATE /secret health SELECT")'],
            cwd=tmp_path,
            env=isolated_environment(tmp_path),
            timeout=10,
        )
    assert "PRIVATE" not in str(error.value)
    with pytest.raises(RuntimeError, match="child_timeout"):
        measure_process(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=tmp_path,
            env=isolated_environment(tmp_path),
            timeout=0.05,
        )


def test_environment_discards_user_configuration_and_credentials(tmp_path, monkeypatch):
    for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "TTI_DB_PATH", "TTI_INGEST_PARITY", "LLM_MODEL"):
        monkeypatch.setenv(key, "PRIVATE_SENTINEL")
    env = isolated_environment(tmp_path)
    assert "PRIVATE_SENTINEL" not in json.dumps(env)
    assert env["TTI_PROVIDER_MODE"] == "local_only"
    assert env["TTI_LOCAL_AUTOSTART"] == env["TTI_LOCAL_STOP_ON_EXIT"] == "0"
    assert Path(env["TTI_DB_PATH"]).parent == tmp_path
    assert Path(env["TTI_APP_STATE_PATH"]).parent == tmp_path
    assert env["TTI_INGEST_FALLBACK_LEGACY"] == "0"


def test_published_models_reject_rows_questions_sql_paths():
    metric = Measurement(name="query_latest_warm", unit="ms", summary=summarize([1, 2, 9]))
    for field in ("rows", "question", "sql", "path", "error", "payload"):
        with pytest.raises(ValidationError):
            Measurement.model_validate({**metric.model_dump(), field: "PRIVATE_SENTINEL"})
    with pytest.raises(ValidationError):
        Measurement(name="/private/query SELECT health", unit="ms", summary=summarize([1]))
    assert "PRIVATE" not in metric.model_dump_json()


def test_bundle_counts_static_transitive_imports_once_and_excludes_lazy(tmp_path):
    (tmp_path / ".vite").mkdir()
    manifest = {
        "index.html": {
            "file": "entry.js",
            "isEntry": True,
            "imports": ["shared"],
            "dynamicImports": ["lazy"],
        },
        "shared": {"file": "shared.js", "imports": ["leaf"]},
        "leaf": {"file": "leaf.js", "imports": ["shared"]},
        "lazy": {"file": "lazy.js"},
    }
    (tmp_path / ".vite/manifest.json").write_text(json.dumps(manifest))
    for name in ("entry", "shared", "leaf", "lazy"):
        (tmp_path / f"{name}.js").write_bytes(name.encode())
    bundle = initial_js_bytes(tmp_path)
    assert bundle.chunks == 3
    assert bundle.raw_bytes == len(b"entrysharedleaf")
    assert bundle.gzip_bytes == sum(
        len(gzip.compress(x, mtime=0)) for x in [b"entry", b"shared", b"leaf"]
    )
    manifest["leaf"]["file"] = "../PRIVATE.js"
    (tmp_path / ".vite/manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="bundle_invalid"):
        initial_js_bytes(tmp_path)


def test_top_level_publication_rejects_unstructured_input():
    from app.bench.report import CaseReport, Report, Runtime

    for model in (CaseReport, Runtime, Report):
        with pytest.raises(ValidationError):
            model.model_validate(
                {"question": "PRIVATE", "sql": "SELECT health", "path": "/private"}
            )


def test_import_and_workload_sampling_defaults_and_overrides():
    from app.bench.synthetic import parse_options

    defaults = parse_options([])
    assert (defaults.ingestion_samples, defaults.ingestion_warmups) == (3, 1)
    assert (defaults.samples, defaults.warmups) == (20, 2)
    pilot = parse_options(
        [
            "--cases",
            "small",
            "--seeds",
            "137",
            "--workers",
            "1",
            "--ingestion-samples",
            "1",
            "--ingestion-warmups",
            "0",
        ]
    )
    assert pilot.cases == ["small"]
    assert (pilot.ingestion_samples, pilot.samples) == (1, 20)
    with pytest.raises(SystemExit):
        parse_options(["--samples", "19"])
    with pytest.raises(SystemExit):
        parse_options(["--ingestion-samples", "0"])
    assert summarize([3, 1, 2]).p95 == 3


async def test_http_rejects_reused_app_state_before_startup(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from app import main
    from app.bench.workload import run_http
    from app.state.app_state import AppStateRepository

    monkeypatch.setenv("TTI_APP_STATE_PATH", str(tmp_path / "already-used.sqlite"))
    repository = AppStateRepository()
    repository.migrate()
    repository.put_cached_response("synthetic", "ds_synthetic", "{}")
    startup = Mock(side_effect=AssertionError("must reject before app startup"))
    monkeypatch.setattr(main, "create_app", startup)
    with pytest.raises(RuntimeError, match="synthetic_app_state_not_fresh"):
        await run_http()
    startup.assert_not_called()


def test_summary_discloses_spread_without_best_of_selection():
    spread = summarize([1.0, 2.0, 3.0])
    assert spread.minimum == 1
    assert spread.maximum == 3
    assert spread.stddev == pytest.approx((2 / 3) ** 0.5)
    assert summarize([7.0]).stddev == 0
