# Supported synthetic maintenance baseline — 22 October 2026

Contract #140, with #141's isolated lifecycle smoke. Source baseline: `49510a7c804bd4c044db87c6e90523cae2ba0602`. Recorded before dependency changes. #142's documentation-only historical reconciliation is included separately; historical test counts are not used as fresh evidence.

## Environment and reproducibility

- macOS 26.6.2 (25G83), Darwin 25.6.0, arm64, Apple M5.
- Node **20.20.2**, npm **10.8.2** from `/opt/homebrew/opt/node@20/bin`; `frontend/.nvmrc` is 20. Global Node 26 was not used for these results.
- CPython **3.12.11**, uv **0.8.17**; `uv sync --directory backend --dev --python 3.12` and Node 20 `npm --prefix frontend ci` both exited 0 before testing.
- Baseline SHA-256 `backend/uv.lock`: `031895e66ac2c52d10123e79ebfd3864d8ec33fcd8b149a15222e480d6f07d86`.
- Baseline SHA-256 `frontend/package-lock.json`: `3385e792b97e96bcd502ec38715e81875cc5ea0b70bf7f482b1f87b752fa3f30`.

Commands run from the repository root with `PATH=/opt/homebrew/opt/node@20/bin:$PATH`, `PYTEST_XDIST_AUTO_NUM_WORKERS=2`, and absolute disposable `TTI_DB_PATH` / `TTI_APP_STATE_PATH` under `/tmp/tti-maintenance-evidence/isolated/`. Test-owned databases use pytest temp directories. No personal export, existing user database, credential or live model was used. Provider tests already mock their gateways; the dedicated smoke additionally forbids inference/health probes and disables local autostart/stop. Relative-date behavior uses fixture dates.

Verify runtimes before repeating:

```bash
node --version
npm --version
node -e 'if (process.versions.node.split(".")[0] !== "20") process.exit(1)'
uv run --directory backend python --version
```

## Fresh command results

Wall times are execution metadata under concurrent sibling-agent load. They are **not** comparable performance measurements or throughput/latency claims. Targeted tests preceded broad gates.

| Exact command | Exit | Observed wall seconds | Result |
| --- | ---: | ---: | --- |
| `uv run --directory backend pytest tests/integration/test_ingest_cli.py tests/integration/test_ingest_phase_contracts.py tests/integration/test_import_activation.py -n 2 -q --no-cov` | 0 | 20.06 | 9 passed; official CLI/phase/activation tests |
| `npm --prefix frontend run test -- --run tests/templates tests/components/template-dispatch.test.tsx tests/api/abort-signal.test.ts --maxWorkers=2` | 0 | 4.56 | 36 passed; six templates, dispatcher, AbortSignal |
| `make check` | 0 | 6.76 | Lint, format, types and version gate passed |
| `make test-backend` | 2 | 21.24 | 456 passed / 4 failed: global autostart override interfered with mocked enabled-path tests |
| `make build` | 0 | 11.17 | Production build passed; sizes below |
| `npm --prefix frontend run test -- --run --coverage --maxWorkers=2` | 0 | 16.57 | 162 tests / 26 files; statements/lines 93.23%, functions 84.02%, branches 81.73% |
| `env -u TTI_LOCAL_AUTOSTART make test-backend` | 0 | 12.4 | 460 passed; 86.13% global coverage |
| `uv run --directory backend coverage report '--include=app/ingest/*' --fail-under=90` | 0 | 0.54 | 912/1012 statements = 90.12%; threshold 90 passed |
| `uv run --directory backend coverage report '--include=app/llm/*' --fail-under=70` | 0 | 0.55 | 1239/1510 statements = 82.05%; threshold 70 passed |
| `npm --prefix frontend run test -- --run tests/api/maintenance-fetch.test.ts --maxWorkers=2` | 0 | 0.67 | 2 passed before dependency changes; real MSW success/cancel |
| `uv run --directory backend pytest tests/integration/test_maintenance_lifecycle.py -n 0 -q --no-cov` | 0 | 0.82 | 1 passed before dependency/workflow changes; official V2 → counts/manifest/relations → restarted readiness |

The first backend attempt incorrectly forced `TTI_LOCAL_AUTOSTART=0` globally. Corrected invocation used `env -u TTI_LOCAL_AUTOSTART make test-backend`; tests of autostart use mocked spawn/health functions and require the default flag. This was an invocation error, not a dependency/application failure. Two initial coverage-report invocations lacked shell quotes around the glob and zsh rejected them before execution (exit 1); the quoted commands above executed successfully. The new smoke's first test-data draft had the wrong step total and the new fetch test's draft used an invalid null narrative; both fixtures were corrected and passed before implementation.

## Synthetic official import evidence

`tests/integration/test_maintenance_lifecycle.py` calls `sys.executable -m app.ingest.run <absolute backend/tests/fixtures/sample.xml> --workers 2 --report-json` from `backend/`, with isolated paths and a 90-second subprocess timeout. Mode is asserted `v2` (no legacy fallback). A separate CLI/phase contract subset also passed at baseline.

| Table | Rows |
| --- | ---: |
| records | 40 |
| record_metadata | 7 |
| hrv_beats | 7 |
| workouts | 3 |
| workout_events | 6 |
| workout_statistics | 8 |
| workout_routes | 2 |
| workout_metadata | 12 |
| activity_summaries | 5 |

All six child-table foreign-key joins have zero orphans. The running workout duration is **45.5 minutes**, step records total **90,954**, and the CLI report's dataset version equals the persisted manifest and restarted `/api/status` version. Readiness is `no_active_import` before import and `ready` afterward; both `/health` responses are `200 {"status":"ok"}`. Gateway inference, local-model autostart and health probes are asserted unused. No background HTTP/model server is launched.

## Baseline production artifact

Vite 6.4.3: 684 modules. Entry JS **1,377.60 kB / 456.41 kB gzip**; CSS 38.32 / 6.86 kB; dashboard chunk 172.17 / 58.26 kB; settings chunk 16.23 / 4.64 kB; diagnostics chunk 5.49 / 1.83 kB. Vite's existing >500 kB chunk warning remains visible; no bundle budget was added or relaxed.

## Explicit pending acceptance

- Per the concurrent-agent operational update, `make bench` and quiet-machine timing/throughput baselines are deferred to the parent. Do not treat existing historical 11 benchmark passes as fresh results. No full-export throughput, browser latency, speedup or live-model-quality claim follows from the fixture or gate wall times.
- The macOS Actions job is implemented and locally reproducible, but remote validation is pending actual PR CI evidence. A local macOS pass is not an Actions pass. Child agents do not watch/poll PRs or CI.
- Parent owns the final integrated review, fallback browser validation, #148 dependency acceptance, merge, post-merge checks and issue receipts. No issue is closed by this batch.

Post-remediation gate results and final lock hashes are recorded in [the dependency disposition](dependency-disposition-2026-10.md). The exact selected scope and residual owners/mitigations are in [the decision](dependency-remediation.md).
