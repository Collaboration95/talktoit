"""Root Makefile forwarding without starting chat or reading a health database."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_make_forwards_cli_options_and_root_relative_paths(tmp_path):
    binary = tmp_path / "uv"
    binary.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    binary.chmod(0o755)
    root = Path(__file__).resolve().parents[3]
    make = shutil.which("make")
    assert make is not None
    question = "How's running? `echo should-stay-literal`"
    result = subprocess.run(  # noqa: S603 - fixed make target with a stub uv, no health data
        [
            make,
            "--no-print-directory",
            "run-cli",
            "INTERACTIVE=1",
            "LOCAL=1",
            "LOCAL_MODEL=installed model",
            "JSON=1",
            "DB_PATH=synthetic folder/fixture.duckdb",
            f"QUESTION={question}",
        ],
        cwd=root,
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )
    args = json.loads(result.stdout)
    assert args == [
        "run",
        "--directory",
        "backend",
        "python",
        "-m",
        "app.cli.chat",
        "--question",
        question,
        "--json",
        "--interactive",
        "--local",
        "--local-model",
        "installed model",
        "--db-path",
        str(root / "synthetic folder" / "fixture.duckdb"),
    ]
    assert result.stderr == ""
