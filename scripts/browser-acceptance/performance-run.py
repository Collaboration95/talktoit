"""Run one functional scenario, or a separately reviewed 2+20 browser group.

Run with the supported uv Python 3.12; uses the existing locked Playwright install.
Never runs a build, downloads a model, reads a user database, or changes a source.
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from run import check, ready, stop

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GIT = shutil.which("git")
NODE = shutil.which("node")
check(GIT and NODE, "required-tools")


def git(source: Path, *args: str) -> str:
    """Read local Git identities with an explicit argv and no shell."""
    return subprocess.check_output([GIT, *args], cwd=source, text=True).strip()  # noqa: S603 - fixed executable/argv; shell is never enabled.


def main() -> int:
    """Generate owned data, run one reviewed protocol group and stop owned sessions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--production-head", required=True)
    parser.add_argument("--role", choices=["main", "reference"], default="main")
    parser.add_argument("--toggle-count", choices=["1", "8"], default="1")
    parser.add_argument(
        "--mode", choices=["functional", "qualification"], default="functional"
    )
    parser.add_argument("--method-review", type=Path)
    parser.add_argument("--channel", choices=["chrome", "chromium"], default="chromium")
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    check(sys.version_info[:2] == (3, 12), "python-3-12-required")
    check(
        subprocess.check_output([NODE, "--version"], text=True).startswith("v20."),  # noqa: S603 - resolved executable and fixed argv; no shell.
        "node-20-required",
    )
    source = args.source.resolve()
    check(
        len(args.production_head) == 40
        and git(source, "rev-parse", args.production_head) == args.production_head,
        "exact-production-head-required",
    )
    identities = {}
    for item in [
        "backend/app",
        "frontend/src",
        "backend/uv.lock",
        "frontend/package-lock.json",
    ]:
        expected = git(source, "rev-parse", f"{args.production_head}:{item}")
        check(
            git(source, "rev-parse", f"HEAD:{item}") == expected,
            "production-source-tree-mismatch",
        )
        check(
            subprocess.run(
                [GIT, "diff", "--quiet", "HEAD", "--", item], cwd=source
            ).returncode  # noqa: S603 - resolved executable and fixed argv; no shell.
            == 0,
            "product-source-dirty",
        )
        identities[item] = expected
    check(
        (source / "frontend/dist/index.html").is_file(),
        "build-source-before-functional-run",
    )
    method_files = [
        HERE / name
        for name in [
            "performance-phase.mjs",
            "performance-render.mjs",
            "performance-report.mjs",
            "performance-browser.mjs",
            "performance-service.py",
            "performance-run.py",
        ]
    ]
    method_hash = hashlib.sha256(
        b"".join(p.name.encode() + b"\x00" + p.read_bytes() for p in method_files)
    ).hexdigest()
    if args.mode == "qualification":
        check(
            args.method_review
            and json.loads(args.method_review.read_text())["status"] == "PASS",
            "independent-method-review-required",
        )
        check(
            subprocess.run(
                [GIT, "diff", "--quiet", "HEAD", "--", str(HERE)], cwd=ROOT
            ).returncode  # noqa: S603 - resolved executable and fixed argv; no shell.
            == 0,
            "committed-harness-required",
        )
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=False)
    private = artifacts / "private"
    private.mkdir(mode=448)
    receipt = {
        "qualification": args.mode == "qualification",
        "production_head": args.production_head,
        "source_checkout_head": git(source, "rev-parse", "HEAD"),
        "harness_head": git(ROOT, "rev-parse", "HEAD"),
        "method_sha256": method_hash,
        "production_identities": identities,
        "locks_sha256": {
            name: hashlib.sha256((source / name).read_bytes()).hexdigest()
            for name in ["backend/uv.lock", "frontend/package-lock.json"]
        },
        "commands": [],
        "cleanup": False,
    }
    if args.method_review:
        receipt["method_review_sha256"] = hashlib.sha256(
            args.method_review.read_bytes()
        ).hexdigest()
    env = {
        key: os.environ[key]
        for key in ["PATH", "TMPDIR", "LANG", "SYSTEMROOT"]
        if key in os.environ
    }
    env.update(
        {
            "PYTHONPATH": os.pathsep.join([str(HERE), str(source / "backend")]),
            "TTI_ACCEPTANCE_PRIVATE": str(private),
            "TTI_DB_PATH": str(private / "health.duckdb"),
            "TTI_APP_STATE_PATH": str(private / "state.sqlite"),
            "TTI_MANIFEST_PATH": str(private / "manifest.json"),
            "TTI_LOCAL_AUTOSTART": "0",
            "TTI_LOCAL_STOP_ON_EXIT": "0",
            "TTI_PROVIDER": "groq",
            "TTI_PROVIDER_MODE": "local_only",
            "TTI_INGEST_WORKERS": "1",
            "PYTEST_XDIST_AUTO_NUM_WORKERS": "2",
        }
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env["TTI_ACCEPTANCE_PORT"] = str(port)
    server = None
    node = None
    exit_code = 1
    try:
        sys.path.insert(0, str(source / "backend"))
        from app.bench.corpus import CASES, write_corpus
        from app.bench.synthetic import _verify_import

        case = CASES["representative" if args.mode == "qualification" else "small"]
        env.update(
            {
                "TTI_INGEST_SHARDS": str(private / "shards"),
                "TTI_INGEST_FALLBACK_LEGACY": "0",
                "TTI_INGEST_PARITY": "0",
                "TTI_DISABLE_SEMANTIC_CANDIDATES": "1",
                "TTI_BENCH_SYNTHETIC": "1",
            }
        )
        corpus = write_corpus(private / "synthetic.xml", case)
        command = [
            sys.executable,
            "-m",
            "app.ingest.run",
            str(private / "synthetic.xml"),
            "--workers",
            "1",
            "--report-json",
        ]
        imported = subprocess.run(  # noqa: S603 - resolved executable and fixed argv; no shell.
            command, cwd=source / "backend", env=env, capture_output=True, text=True
        )
        receipt["commands"].append(
            {"stage": "official_import", "argv": command, "exit": imported.returncode}
        )
        (private / "import-private.log").write_text(imported.stdout + imported.stderr)
        check(imported.returncode == 0, "official-import-failed")
        generation = _verify_import(env, imported.stdout, case, corpus, 1)
        receipt["corpus_sha256"] = corpus.sha256
        receipt["parity_verified"] = True
        with (private / "server-private.log").open("w") as log:
            server = subprocess.Popen(  # noqa: S603 - resolved executable and fixed argv; no shell.
                [sys.executable, str(HERE / "performance-service.py")],
                cwd=private,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            ready(server, f"http://127.0.0.1:{port}")
            command = [
                NODE,
                str(HERE / "performance-browser.mjs"),
                "--generation",
                generation,
                "--base",
                f"http://127.0.0.1:{port}",
                "--private",
                str(private),
                "--mode",
                args.mode,
                "--role",
                args.role,
                "--head",
                args.production_head,
                "--harness",
                method_hash,
                "--toggle-count",
                args.toggle_count,
            ]
            if args.channel == "chrome":
                command += ["--channel", "chrome"]
            if args.method_review:
                command += ["--review", str(args.method_review.resolve())]
            node_env = {
                **env,
                **{
                    key: os.environ[key]
                    for key in ["HOME", "PLAYWRIGHT_BROWSERS_PATH"]
                    if key in os.environ
                },
            }
            node = subprocess.Popen(  # noqa: S603 - resolved executable and fixed argv; no shell.
                command,
                cwd=ROOT,
                env=node_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            output, _ = node.communicate(
                timeout=300 if args.mode == "functional" else 900
            )
            (private / "browser-private.log").write_text(output)
            receipt["commands"].append(
                {"stage": "browser", "argv": command, "exit": node.returncode}
            )
            print(output, end="", flush=True)
            exit_code = node.returncode
    except Exception as error:
        receipt["failure"] = type(error).__name__
        (private / "controller-failure-private.txt").write_text(str(error))
    finally:
        if node is not None:
            stop(node, private)
        if server is not None:
            stop(server, private)
        receipt["cleanup"] = True
        receipt["exit_code"] = exit_code
        (artifacts / "receipt-private.json").write_text(json.dumps(receipt, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
