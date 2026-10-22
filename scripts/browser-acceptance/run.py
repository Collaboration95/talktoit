"""Supervise isolated production browser acceptance on macOS or Ubuntu.

Run with the locked backend Python 3.12 environment, after building frontend.
Only screenshots and the sanitized receipt survive the TemporaryDirectory.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def check(value: object, criterion: str) -> None:
    """Raise only a public, fixed criterion identifier."""
    if not value:
        raise RuntimeError(criterion)


def descendants(root: int) -> set[int]:
    """Observe only PID relationships; never read another process environment."""
    rows = subprocess.check_output(["ps", "-axo", "pid=,ppid=,pgid="], text=True)
    relationships = [tuple(map(int, row.split())) for row in rows.splitlines()]
    owned = {root}
    while True:
        expanded = owned | {pid for pid, parent, _ in relationships if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    return {group for pid, _, group in relationships if pid in owned}


def stop(process: subprocess.Popen, private: Path, *, hard: bool = False) -> None:
    """Stop owned sessions, including importer sessions detached by the real API."""
    groups = {process.pid} | descendants(process.pid)
    if process.args[-1] == str(HERE / "service.py"):
        ledger = private / "process-groups"
        if ledger.exists():
            active = set()
            for line in ledger.read_text().splitlines():
                pid = int(line)
                if pid > 0:
                    active.add(pid)
                else:
                    active.discard(-pid)
            groups |= active
    check(os.getpgrp() not in groups, "process-ownership")
    for group in groups:
        try:
            os.killpg(group, signal.SIGKILL if hard else signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # Always reap remaining descendants before deleting their temporary files.
    for group in groups:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = subprocess.check_output(["ps", "-axo", "pgid=,stat="], text=True)
        live = {
            int(row.split()[0])
            for row in rows.splitlines()
            if not row.split()[1].startswith("Z")
        }
        if not groups & live:
            return
        time.sleep(0.05)
    raise RuntimeError("owned-processes-remain")


def ready(process: subprocess.Popen, base: str) -> None:
    """Wait for actual loopback HTTP readiness, with a bounded deadline."""
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        check(process.poll() is None, "backend-start-exit")
        try:
            with urllib.request.urlopen(base + "/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise RuntimeError("backend-readiness-timeout")


def main() -> int:
    """Generate synthetic inputs, run browser phases, hard-restart, and clean up."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()

    def interrupted(_signal: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    check(not any(artifacts.iterdir()), "artifacts-must-be-empty")
    receipt = {
        "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "platform": platform.system(),
        "python": platform.python_version(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "criteria": {},
        "exits": {},
    }
    server = None
    node = None
    stage = "runtime"
    exit_code = 1
    with tempfile.TemporaryDirectory(prefix="tti-browser-acceptance-") as temporary:
        private = Path(temporary).resolve()
        try:
            check(sys.version_info[:2] == (3, 12), "python-3-12-required")
            check(receipt["node"].startswith("v20."), "node-20-required")
            check(
                (ROOT / "frontend/dist/index.html").is_file(),
                "production-build-required",
            )
            check(
                subprocess.run(
                    [
                        "git",
                        "diff",
                        "--quiet",
                        "HEAD",
                        "--",
                        "backend/app",
                        "frontend/src",
                    ],
                    cwd=ROOT,
                ).returncode
                == 0,
                "committed-product-source-required",
            )
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            # Allowlist runtime variables: never pass inherited provider keys, proxy
            # credentials, user data paths, PYTHONPATH, or model configuration.
            env = {
                key: os.environ[key]
                for key in ("PATH", "TMPDIR", "LANG", "SYSTEMROOT")
                if key in os.environ
            }
            env.update(
                {
                    "PYTHONPATH": os.pathsep.join([str(HERE), str(ROOT / "backend")]),
                    "TTI_ACCEPTANCE_PRIVATE": str(private),
                    "TTI_ACCEPTANCE_PORT": str(port),
                    "TTI_DB_PATH": str(private / "health.duckdb"),
                    "TTI_APP_STATE_PATH": str(private / "state.sqlite"),
                    "TTI_LOCAL_AUTOSTART": "0",
                    "TTI_LOCAL_STOP_ON_EXIT": "0",
                    "TTI_PROVIDER": "groq",
                    "TTI_PROVIDER_MODE": "local_only",
                    "TTI_INGEST_WORKERS": "2",
                    "PYTEST_XDIST_AUTO_NUM_WORKERS": "2",
                    "OMP_NUM_THREADS": "2",
                    "OPENBLAS_NUM_THREADS": "2",
                }
            )
            # Use the repository generator; never ingest an external path.
            sys.path.insert(0, str(ROOT / "backend"))
            from app.bench.corpus import CASES, CorpusSpec, write_corpus

            stage = "generate-corpus"
            write_corpus(private / "lifecycle.xml", CASES["representative"])
            write_corpus(
                private / "zero.xml", CorpusSpec("small", records=4, workouts=1, days=2)
            )
            # Copy XML alone, deliberately without the committed companion GPX.
            (private / "sample.xml").write_bytes(
                (ROOT / "backend/tests/fixtures/sample.xml").read_bytes()
            )

            def start() -> subprocess.Popen:
                nonlocal server
                server = subprocess.Popen(
                    [sys.executable, str(HERE / "service.py")],
                    cwd=private,
                    env=env,
                    stdout=server_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                ready(server, base)
                return server

            with (private / "server.log").open("w") as server_log:
                stage = "start-backend"
                server = start()
                for phase in ("journey", "recovery"):
                    stage = phase
                    node = subprocess.Popen(
                        [
                            "node",
                            str(HERE / "browser.mjs"),
                            phase,
                            base,
                            str(private),
                            str(artifacts),
                            sys.executable,
                        ],
                        cwd=ROOT,
                        env={
                            **env,
                            **{
                                key: os.environ[key]
                                for key in ("HOME", "PLAYWRIGHT_BROWSERS_PATH")
                                if key in os.environ
                            },
                        },
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        start_new_session=True,
                    )
                    output, _ = node.communicate(timeout=240)
                    # Browser stdout contains only fixed criterion IDs and booleans.
                    print(output, end="", flush=True)
                    receipt["exits"][phase] = node.returncode
                    phase_receipt = private / f"{phase}.json"
                    if phase_receipt.exists():
                        receipt["criteria"].update(
                            json.loads(phase_receipt.read_text())
                        )
                    runtime = private / "browser-runtime.json"
                    if runtime.exists():
                        receipt["browser"] = json.loads(runtime.read_text())
                    stop(node, private)
                    # Accumulated layout failures must not prevent the crash /
                    # durable recovery evidence. Missing handoff means a fatal
                    # prerequisite failed and dependent recovery cannot proceed.
                    if phase == "journey":
                        check(
                            (private / "handoff.json").exists(),
                            "journey-prerequisite-failed",
                        )
                    node = None
                    if phase == "journey":
                        stage = "hard-stop"
                        # Kill the actual backend and detached official importer, as
                        # a process-tree crash; no graceful shutdown/job mutation.
                        stop(server, private, hard=True)
                        receipt["exits"]["hard_stop"] = server.returncode
                        check(server.returncode == -signal.SIGKILL, "backend-hard-stop")
                        server = None
                        server = start()
                check((private / "safety-installed").exists(), "safety-installed")
                events = (
                    (private / "denials").read_text().splitlines()
                    if (private / "denials").exists()
                    else []
                )
                for kind in ("tcp", "dns", "private_file"):
                    receipt["criteria"][f"no-{kind}-attempts"] = kind not in events
                # Only explicit open-ended fallback planning can reach the shim;
                # it is rejected before any client/provider execution.
                check(
                    set(events) <= {"provider"}, "no-network-or-private-file-attempts"
                )
                receipt["criteria"]["provider-execution-denied"] = True
                exit_code = (
                    0
                    if all(receipt["criteria"].values())
                    and all(
                        receipt["exits"][phase] == 0
                        for phase in ("journey", "recovery")
                    )
                    else 1
                )
        except BaseException as error:
            receipt["failure"] = stage
            receipt["error_type"] = type(error).__name__
            if str(error).replace("-", "").isalpha():
                receipt["failure_criterion"] = str(error)
            print(
                json.dumps({"failed": stage, "error_type": type(error).__name__}),
                flush=True,
            )
        finally:
            for process in (node, server):
                if process is not None:
                    stop(process, private)
            receipt["criteria"]["owned-process-cleanup"] = True
            receipt["exit"] = exit_code
            (artifacts / "receipt.json").write_text(
                json.dumps(receipt, indent=2) + "\n"
            )
    print(
        json.dumps(
            {"exit": exit_code, "temporary_storage_removed": not private.exists()}
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
