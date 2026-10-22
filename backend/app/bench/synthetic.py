"""Opt-in synthetic baseline CLI. Never accepts a user XML/database path."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast
from unittest.mock import patch

import duckdb

from app.bench.corpus import CASES, Corpus, CorpusSpec, verify_database, write_corpus
from app.bench.process import measure_process
from app.bench.report import (
    INGESTION_METRICS,
    Bundle,
    CaseReport,
    Join,
    Measurement,
    MetricName,
    Panel,
    PlanEvidence,
    PlanVariant,
    Report,
    Runtime,
    Sampling,
    Table,
    summarize,
)
from app.bench.workload import WorkloadResult
from app.db.connection import dataset_snapshot

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
INTERVAL = 0.05


def isolated_environment(directory: Path) -> dict[str, str]:
    """Inherit tool discovery only; discard all credentials and user app options."""
    directory = directory.resolve()
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG") if key in os.environ}
    env.update(
        {
            "TMPDIR": str(directory),
            "PYTHONUTF8": "1",
            "TTI_BENCH_SYNTHETIC": "1",
            "TTI_DB_PATH": str(directory / "health.duckdb"),
            "TTI_APP_STATE_PATH": str(directory / "state.sqlite"),
            "TTI_INGEST_SHARDS": str(directory / "shards"),
            "TTI_INGEST_FALLBACK_LEGACY": "0",
            "TTI_INGEST_PARITY": "0",
            "TTI_LOCAL_AUTOSTART": "0",
            "TTI_LOCAL_STOP_ON_EXIT": "0",
            "TTI_PROVIDER": "local",
            "TTI_PROVIDER_MODE": "local_only",
            "TTI_DISABLE_SEMANTIC_CANDIDATES": "1",
        }
    )
    return env


def initial_js_bytes(dist: Path) -> Bundle:
    """Sum unique initial entry/static imports from a fresh Vite manifest."""
    manifest = json.loads((dist / ".vite/manifest.json").read_text())
    pending = [key for key, value in manifest.items() if value.get("isEntry")]
    visited: set[str] = set()
    files: set[Path] = set()
    raw = compressed = 0
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        item = manifest[key]
        path = (dist / item["file"]).resolve()
        if not path.is_relative_to(dist.resolve()) or path.suffix != ".js":
            raise ValueError("bundle_invalid")
        if path not in files:
            content = path.read_bytes()
            raw += len(content)
            compressed += len(gzip.compress(content, mtime=0))
            files.add(path)
        pending.extend(item.get("imports", []))
    return Bundle(chunks=len(files), raw_bytes=raw, gzip_bytes=compressed)


def _verify_import(
    env: dict[str, str], output: str, spec: CorpusSpec, corpus: Corpus, workers: int
) -> str:
    # Scope the public default-path APIs to this generated-only subprocess configuration.
    with patch.dict(os.environ, env, clear=True), dataset_snapshot() as snapshot:
        private_report = json.loads(output.splitlines()[-1])
        manifest = snapshot.dataset
        if (
            private_report["mode"] != "v2"
            or private_report["resolved_workers"] != workers
            or manifest is None
            or snapshot.generation is None
            or private_report["dataset_version_id"] != manifest.id
            or any(manifest.counts.get(key) != value for key, value in corpus.counts.items())
        ):
            raise RuntimeError("synthetic_activation_failed")
        verify_database(snapshot.connection, spec, corpus)
        return manifest.id


def run_case(
    directory: Path,
    spec: CorpusSpec,
    *,
    workers: int,
    ingestion_warmups: int = 1,
    ingestion_samples: int = 3,
    warmups: int = 2,
    samples: int = 20,
    timeout: float = 1800,
) -> CaseReport:
    """Sample imports independently, then reuse one verified immutable generation.

    Every workload subprocess has fresh app state. Its real application startup
    projects the same committed generation through the production lifecycle API.
    No pointer, generation manifest or SQLite lifecycle protocol is duplicated.
    """
    if (
        workers < 1
        or min(warmups, ingestion_warmups) < 0
        or min(samples, ingestion_samples) < 1
        or timeout <= 0
    ):
        raise ValueError("run_options_invalid")
    directory.mkdir(parents=True, exist_ok=True)
    source = (directory / "synthetic.xml").resolve()
    corpus = write_corpus(source, spec)
    values: dict[MetricName, list[float]] = {}
    requests: dict[Panel, int] = {}
    plans: dict[Join, bool] = {}
    variants: dict[PlanVariant, PlanEvidence] = {}
    memory_samples = 0
    plan_runs = 0
    shared_env: dict[str, str] = {}
    generation_id = ""
    with ExitStack() as owned:
        import_trials = ingestion_warmups + ingestion_samples
        for trial in range(import_trials):
            temporary = tempfile.TemporaryDirectory(prefix="import-", dir=directory)
            trial_dir = Path(owned.enter_context(temporary))
            env = isolated_environment(trial_dir)
            ingestion = measure_process(
                [
                    sys.executable,
                    "-m",
                    "app.ingest.run",
                    str(source),
                    "--workers",
                    str(workers),
                    "--report-json",
                ],
                cwd=BACKEND,
                env=env,
                interval=INTERVAL,
                timeout=timeout,
            )
            generation_id = _verify_import(env, ingestion.stdout, spec, corpus, workers)
            if trial >= ingestion_warmups:
                observed: dict[MetricName, float] = {
                    "ingest_full_wall": ingestion.elapsed_ms,
                    "ingest_tree_peak_rss": float(ingestion.peak_rss_bytes),
                    "ingest_rows_per_second": sum(corpus.counts.values())
                    / (ingestion.elapsed_ms / 1000),
                }
                for key, value in observed.items():
                    values.setdefault(key, []).append(value)
                memory_samples += ingestion.memory_samples
            if trial < import_trials - 1:
                temporary.cleanup()
            else:
                shared_env = env
        for trial in range(warmups + samples):
            with tempfile.TemporaryDirectory(prefix="request-", dir=directory) as trial_name:
                env = isolated_environment(Path(trial_name))
                # Keep the configured managed target; never dereference its legacy file.
                env["TTI_DB_PATH"] = shared_env["TTI_DB_PATH"]
                env["TTI_BENCH_GENERATION_ID"] = generation_id
                env["TTI_BENCH_PLAN_MATRIX"] = "1" if trial == warmups else "0"
                workload = measure_process(
                    [
                        sys.executable,
                        "-m",
                        "app.bench.workload",
                    ],
                    cwd=BACKEND,
                    env=env,
                    interval=INTERVAL,
                    timeout=timeout,
                )
                measured = WorkloadResult.model_validate_json(workload.stdout.splitlines()[-1])
                if (
                    measured.provider_network_calls
                    or not measured.cold_cache_verified
                    or not measured.managed_generation_verified
                ):
                    raise RuntimeError("synthetic_workload_isolation_failed")
                if measured.plan_variants:
                    plan_runs += 1
                    if variants:
                        raise RuntimeError("synthetic_plan_matrix_repeated")
                    variants, plans = measured.plan_variants, measured.explain_analyze
                if trial < warmups:
                    continue
                values.setdefault("workload_process_wall", []).append(workload.elapsed_ms)
                for key, value in measured.metrics.items():
                    values.setdefault(key, []).append(value)
                requests = measured.dashboard_requests
    measurements = [
        Measurement(
            name=name,
            group="ingestion" if name in INGESTION_METRICS else "workload",
            unit=(
                "bytes"
                if name == "ingest_tree_peak_rss"
                else "rows/s"
                if name == "ingest_rows_per_second"
                else "calls"
                if name == "profile_calls"
                else "ms"
            ),
            summary=summarize(observations),
        )
        for name, observations in values.items()
    ]
    return CaseReport(
        case=spec.name,
        seed=spec.seed,
        source_sha256=corpus.sha256,
        source_bytes=corpus.source_bytes,
        counts=cast(dict[Table, int], corpus.counts),
        workers=workers,
        ingestion_sampling=Sampling(warmups=ingestion_warmups, samples=ingestion_samples),
        workload_sampling=Sampling(warmups=warmups, samples=samples),
        measurements=measurements,
        parity_verified=True,
        cold_cache_isolated=True,
        managed_generation_verified=True,
        dashboard_requests=requests,
        explain_analyze=plans,
        plan_variants=variants,
        plan_matrix_runs=plan_runs,
        memory_interval_ms=INTERVAL * 1000,
        memory_samples=memory_samples,
    )


def _command(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()  # noqa: S603


def runtime_metadata() -> Runtime:
    """Record current supported runtime and lock identities without hostnames."""
    if platform.system() == "Darwin":
        cpu_model = _command(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"])
        memory = int(_command(["/usr/sbin/sysctl", "-n", "hw.memsize"]))
    else:
        cpu_model = platform.machine()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
        memory = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    return Runtime(
        os=cast(Literal["Darwin", "Linux"], platform.system()),
        os_release=platform.release(),
        architecture=cast(Literal["arm64", "aarch64", "x86_64", "AMD64"], platform.machine()),
        logical_cpus=os.cpu_count() or 1,
        cpu_model=cpu_model,
        physical_memory_bytes=memory,
        duckdb=duckdb.__version__,
        npm=_command(["npm", "--version"]),
        worktree_dirty=bool(_command(["git", "status", "--porcelain"])),
        python=platform.python_version(),
        node=_command(["node", "--version"]),
        revision=_command(["git", "rev-parse", "HEAD"]),
        backend_lock_sha256=hashlib.sha256((BACKEND / "uv.lock").read_bytes()).hexdigest(),
        frontend_lock_sha256=hashlib.sha256(
            (ROOT / "frontend/package-lock.json").read_bytes()
        ).hexdigest(),
    )


def parse_options(argv: list[str] | None = None) -> argparse.Namespace:
    """Validate independent import and inexpensive workload sampling options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=list(CASES))
    parser.add_argument("--seeds", nargs="+", type=int, default=[137, 271])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--ingestion-warmups", type=int, default=1)
    parser.add_argument("--ingestion-samples", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args(argv)
    if (
        min(args.workers) < 1
        or min(args.warmups, args.ingestion_warmups) < 0
        or args.samples < 20
        or args.ingestion_samples < 1
        or args.timeout <= 0
    ):
        parser.error("require >=20 workload samples, >=1 import sample, nonnegative warmups")
    return args


def main() -> None:
    """Print a single validated report, using disposable generated-only storage."""
    args = parse_options()
    runtime = runtime_metadata()  # validates Node 20 before expensive work
    bundle = initial_js_bytes(ROOT / "frontend/dist")
    cases: list[CaseReport] = []
    with tempfile.TemporaryDirectory(prefix="tti-synthetic-") as temporary:
        for name in args.cases:
            for seed in args.seeds:
                for workers in args.workers:
                    directory = Path(temporary) / f"{name}-{seed}-{workers}"
                    cases.append(
                        run_case(
                            directory,
                            replace(CASES[name], seed=seed),
                            workers=workers,
                            ingestion_warmups=args.ingestion_warmups,
                            ingestion_samples=args.ingestion_samples,
                            warmups=args.warmups,
                            samples=args.samples,
                            timeout=args.timeout,
                        )
                    )
    print(Report(runtime=runtime, bundle=bundle, cases=cases).model_dump_json(indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Paths, validation input values and subprocess logs must stay private.
        print('{"status":"synthetic_benchmark_failed"}', file=sys.stderr)
        raise SystemExit(1) from None
