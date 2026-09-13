"""CLI coverage for argument ordering and worker configuration parsing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


def _run_ingest(tmp_path: Path, name: str, extra_args: list[str], **env_overrides: str):
    """Run the ingest CLI in a subprocess and return (report, stderr)."""
    env = os.environ.copy()
    env.update(
        {
            "TTI_DB_PATH": str(tmp_path / f"{name}.duckdb"),
            "TTI_APP_STATE_PATH": str(tmp_path / f"{name}-state.sqlite"),
            "TTI_LOCAL_AUTOSTART": "0",
        }
    )
    env.update(env_overrides)
    command = [
        sys.executable,
        "-m",
        "app.ingest.run",
        str(FIXTURE),
        *extra_args,
        "--report-json",
    ]
    result = subprocess.run(  # noqa: S603
        command,
        cwd=FIXTURE.parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    return report, result.stderr


def test_ingest_cli_accepts_worker_flag_after_path(tmp_path: Path) -> None:
    """The documented 'export.xml --workers N' order resolves N, not 'File not found: 1'."""
    report, _ = _run_ingest(tmp_path, "flag", ["--workers", "2"])
    assert report["resolved_workers"] == 2


def test_ingest_cli_flag_overrides_environment(tmp_path: Path) -> None:
    """An explicit flag wins over the environment value."""
    report, _ = _run_ingest(tmp_path, "override", ["--workers", "2"], TTI_INGEST_WORKERS="4")
    assert report["resolved_workers"] == 2


def test_ingest_cli_resolves_numeric_environment(tmp_path: Path) -> None:
    """The environment-only path resolves and reports the configured worker count."""
    report, _ = _run_ingest(tmp_path, "env-numeric", [], TTI_INGEST_WORKERS="2")
    assert report["resolved_workers"] == 2


def test_ingest_cli_auto_environment_uses_policy(tmp_path: Path) -> None:
    """'auto' falls back to the size-based policy (one worker for a small export)."""
    report, stderr = _run_ingest(tmp_path, "env-auto", [], TTI_INGEST_WORKERS="auto")
    assert report["resolved_workers"] == 1
    assert "Invalid TTI_INGEST_WORKERS" not in stderr


def test_ingest_cli_invalid_environment_falls_back(tmp_path: Path) -> None:
    """A non-numeric worker value must not abort the import, and must be visible."""
    report, stderr = _run_ingest(tmp_path, "env-invalid", [], TTI_INGEST_WORKERS="not-a-number")
    assert report["resolved_workers"] == 1
    assert "Invalid TTI_INGEST_WORKERS='not-a-number'; using auto policy" in stderr
