"""CLI coverage for argument ordering and worker configuration parsing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"


@pytest.mark.parametrize("worker_env", ["auto", "not-a-number"])
def test_ingest_cli_accepts_worker_flag_and_environment(tmp_path: Path, worker_env: str) -> None:
    """The documented path/flag order and tolerant env values complete successfully."""
    env = os.environ.copy()
    env.update(
        {
            "TTI_INGEST_WORKERS": worker_env,
            "TTI_DB_PATH": str(tmp_path / "health.duckdb"),
            "TTI_APP_STATE_PATH": str(tmp_path / "state.sqlite"),
            "TTI_LOCAL_AUTOSTART": "0",
        }
    )
    command = [
        sys.executable,
        "-m",
        "app.ingest.run",
        str(FIXTURE),
        "--workers",
        "2",
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
    assert report["resolved_workers"] == 2
    env.pop("TTI_INGEST_WORKERS")
    env["TTI_INGEST_WORKERS"] = worker_env
    env["TTI_DB_PATH"] = str(tmp_path / "health-env.duckdb")
    env["TTI_APP_STATE_PATH"] = str(tmp_path / "state-env.sqlite")
    env_result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.ingest.run", str(FIXTURE), "--report-json"],
        cwd=FIXTURE.parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert env_result.returncode == 0, env_result.stderr
