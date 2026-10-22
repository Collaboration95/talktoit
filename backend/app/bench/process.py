"""Bounded subprocess measurements using the same RSS units on Linux/macOS."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path


def tree_rss_bytes(snapshot: str, root_pid: int) -> int:
    """Sum RSS of the root and descendants in one ps snapshot (KiB to bytes)."""
    rows: dict[int, tuple[int, int]] = {}
    try:
        for line in snapshot.splitlines():
            pid, parent, rss = map(int, line.split())
            rows[pid] = (parent, rss)
    except ValueError:
        raise ValueError("memory_snapshot_invalid") from None
    descendants = {root_pid}
    while True:
        new = {pid for pid, (parent, _) in rows.items() if parent in descendants}
        if new <= descendants:
            break
        descendants.update(new)
    return sum(rss for pid, (_, rss) in rows.items() if pid in descendants) * 1024


@dataclass(frozen=True)
class ProcessResult:
    """Private child output plus safe numeric measurements."""

    elapsed_ms: float
    peak_rss_bytes: int
    memory_samples: int
    stdout: str


def measure_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    interval: float = 0.05,
    timeout: float = 1800,
) -> ProcessResult:
    """Measure through child exit; discard stderr and fail without leaking logs.

    Each snapshot is `ps -axo pid=,ppid=,rss=`. Peak is the maximum simultaneous
    sum, not a sum of independently observed per-process peaks. Short-lived
    workers can escape sampling; RSS double-counts shared pages. No PSS/USS or
    resource.getrusage platform-unit assumptions are made.
    """
    if interval <= 0 or timeout <= 0:
        raise ValueError("process_options_invalid")
    started = time.perf_counter()
    peak = samples = 0
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(  # noqa: S603 - internal argument arrays, no shell
            command,
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        ) as child:
            stop = threading.Event()

            def sample() -> None:
                nonlocal peak, samples
                while not stop.is_set():
                    snapshot = subprocess.run(
                        ["/bin/ps", "-axo", "pid=,ppid=,rss="],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=5,
                    )
                    rss = tree_rss_bytes(snapshot.stdout, child.pid)
                    if rss:
                        peak = max(peak, rss)
                        samples += 1
                    stop.wait(interval)

            with ThreadPoolExecutor(max_workers=1) as sampler:
                future = sampler.submit(sample)
                try:
                    try:
                        child.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError("child_timeout") from None
                    # Timestamp immediately after wait, before sampler finalization.
                    elapsed = (time.perf_counter() - started) * 1000
                    if child.returncode != 0:
                        raise RuntimeError("child_failed")
                finally:
                    stop.set()
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                future.result()
                if not samples:
                    raise RuntimeError("memory_unobserved")
        output.seek(0)
        return ProcessResult(elapsed, peak, samples, output.read().decode())
