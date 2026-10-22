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
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

import duckdb

from app.bench.corpus import CASES, CorpusSpec, verify_database, write_corpus
from app.bench.process import measure_process
from app.bench.report import (
    Bundle,
    CaseReport,
    Join,
    Measurement,
    MetricName,
    Panel,
    Report,
    Runtime,
    Table,
    summarize,
)
from app.bench.workload import WorkloadResult
from app.state.app_state import AppStateRepository

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


def run_case(
    directory: Path,
    spec: CorpusSpec,
    *,
    workers: int,
    warmups: int,
    samples: int,
    timeout: float = 1800,
) -> CaseReport:
    """Run full CLI imports and fresh-process workloads; discard warmup trials."""
    if workers < 1 or warmups < 0 or samples < 1:
        raise ValueError("run_options_invalid")
    directory.mkdir(parents=True, exist_ok=True)
    source = (directory / "synthetic.xml").resolve()
    corpus = write_corpus(source, spec)
    values: dict[MetricName, list[float]] = {}
    requests: dict[Panel, int] = {}
    plans: dict[Join, bool] = {}
    memory_samples = 0
    for trial in range(warmups + samples):
        with tempfile.TemporaryDirectory(prefix="trial-", dir=directory) as trial_name:
            trial_dir = Path(trial_name)
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
            private_report = json.loads(ingestion.stdout.splitlines()[-1])
            manifest = AppStateRepository(Path(env["TTI_APP_STATE_PATH"])).get_active()
            if (
                private_report["mode"] != "v2"
                or private_report["resolved_workers"] != workers
                or manifest is None
                or private_report["dataset_version_id"] != manifest.id
                or any(manifest.counts.get(key) != value for key, value in corpus.counts.items())
            ):
                raise RuntimeError("synthetic_activation_failed")
            with duckdb.connect(env["TTI_DB_PATH"], read_only=True) as conn:
                verify_database(conn, spec, corpus)
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
            if measured.provider_network_calls:
                raise RuntimeError("network_attempt_detected")
            if trial < warmups:
                continue
            observed: dict[MetricName, float] = {
                **measured.metrics,
                "ingest_full_wall": ingestion.elapsed_ms,
                "ingest_tree_peak_rss": float(ingestion.peak_rss_bytes),
                "ingest_rows_per_second": sum(corpus.counts.values())
                / (ingestion.elapsed_ms / 1000),
            }
            for key, value in observed.items():
                values.setdefault(key, []).append(value)
            requests, plans = measured.dashboard_requests, measured.explain_analyze
            memory_samples += ingestion.memory_samples
    measurements = [
        Measurement(
            name=name,
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
        warmups=warmups,
        samples=samples,
        measurements=measurements,
        parity_verified=True,
        dashboard_requests=requests,
        explain_analyze=plans,
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


def main() -> None:
    """Print a single validated report, using disposable generated-only storage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=tuple(CASES), default=list(CASES))
    parser.add_argument("--seeds", nargs="+", type=int, default=[137, 271])
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2])
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()
    if min(args.workers) < 1 or args.warmups < 0 or args.samples < 1 or args.timeout <= 0:
        parser.error("invalid sampling options")
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
