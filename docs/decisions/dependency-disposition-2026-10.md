# Dependency disposition and gate evidence — 22 October 2026

Refs #140 #141 #142 #144 #145 #146 #147. Follow [the bounded decision](dependency-remediation.md) and [the supported baseline](maintenance-baseline-2026-10.md). This is an implementation handoff for the parent's final integrated review and #148; it is not a post-merge completion receipt.

## Final locked scope

Python remains >=3.12; validation used CPython 3.12.11. Only four Python resolved versions changed: anyio **4.14.2**, certifi **2026.10.19**, pip **26.2** (normalized 26.2.0), urllib3 **2.8.0**. No backend manifest/runtime API migration was needed. pip/urllib3 findings originate in development auditing tooling; they were fixed in the lock, not ignored.

Node remains **20.20.2**, npm **10.8.2**. Compatible batch: Vite **6.4.5**, undici **7.30.1**, PostCSS **8.5.31**, baseline-browser-mapping **2.11.30**, browserslist **4.29.4**, nanoid **3.3.20**, source-map-js **1.2.2**, with browserslist data updates. The separate bounded compatibility step locks **Vitest and coverage-v8 4.1.12** together and removes tinypool and the old coverage/glob/brace-expansion chain. Its required Chai 6, std-env 4 and AST mapping transitives are confined to the test tooling. No application imports, chart dependencies, styles, six-template contracts or Vite/Tailwind configuration changed. Runtime dependency versions are unchanged.

Ruff's staged hook now pins **0.15.20**, matching the backend lock, with canonical `ruff-check` / `ruff-format`. Existing Ubuntu jobs and coverage thresholds are unchanged. The new macOS job uses locked Python 3.12 / Node 20 installs, temporary paths, disabled autostart, forbidden model operations, and no background web server. The audit workflow uses a locked Python 3.12 environment and a Node 20 `npm ci`; neither audit is optional.

| Final lock | SHA-256 |
| --- | --- |
| `backend/uv.lock` | `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b` |
| `frontend/package-lock.json` | `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c` |

## Fresh audit dispositions

| Command | Baseline exit / result | Final exit / result |
| --- | --- | --- |
| `uv run --directory backend pip-audit --format=json` | 1 / 9 findings in 4 packages | **0 / no known vulnerabilities** |
| `npm --prefix frontend audit --json` | 1 / 18 packages: 4 moderate, 12 high, 2 critical | **1 / 7 packages: 2 moderate, 5 high, 0 critical** |
| `npm --prefix frontend audit --omit=dev --json` | 0 / no vulnerabilities | **0 / no vulnerabilities** |
| `npm --prefix frontend ls --all` | 1 / Tremor's pre-existing React ^18 peer mismatch | **1 / same mismatch** |

All selected Python IDs disappeared: PYSEC-2026-4025/4023/4024 (AnyIO), PYSEC-2026-4320 (certifi), PYSEC-2026-3721 (pip; duplicate scanner entry for one ID), PYSEC-2026-4177/4176/4175 (urllib3). None was ignored.

The Vitest migration removes GHSA-82fw-gwwq-j7x9 and GHSA-qxg6-89mg-rqv8 from mocker/Vitest, and GHSA-5gmw-xhrv-c9v3 / GHSA-85c8-ppgw-ccpr by removing tinypool. Compatible fixes remove the baseline Vite, undici, browser data, PostCSS, nanoid and source-map-js IDs listed in the decision. The migration also removes all vulnerable brace-expansion copies from the final lock. Fresh audits, not npm's suggested force upgrade, determine the outcome.

### Unresolved advisory inventory (complete)

| Advisory | Final vulnerable packages / paths | Owner, risk, mitigation, next action |
| --- | --- | --- |
| GHSA-vfj7-8cjw-p6xm | `tailwindcss@3.4.19 → chokidar@3.6.0 / fast-glob@3.3.3 → micromatch@4.0.8 → braces@3.0.3` (braces is also direct under chokidar) | Maintenance owner, parent #148 / high stack-exhaustion DoS for untrusted glob input / compile trusted repository CSS/config only, loopback development server, never derive patterns from uploaded data / patched braces 3 or tested Tailwind 3 backport; otherwise separate coordinated Tremor/Tailwind decision. |
| GHSA-rj75-hqrm-r3gf | `tailwindcss@3.4.19 → postcss-selector-parser@6.1.4`, also through `postcss-nested@6.2.0` | Maintenance owner, parent #148 / moderate CPU-exhaustion DoS for malicious selectors / compile trusted CSS only, never interpret health values as selectors / fix requires >=7.1.6; separately verify a backport/major transitive API migration or coordinated styling migration. |

These two underlying advisories propagate to the seven reported packages (braces, chokidar, fast-glob, micromatch, postcss-nested, postcss-selector-parser, tailwindcss). npm's proposed Tailwind 4.3.3 switch is incompatible with this batch's Tremor 3/Tailwind 3 boundary. No safe contained Tailwind migration is asserted. **The enabled `npm audit --audit-level=moderate` gate remains red**, with no blanket ignore, forced upgrade, audit threshold change or `continue-on-error`. Production-only audit success does not waive that gate.

The existing Tremor 3 / React 19 peer mismatch remains explicit (`legacy-peer-deps=true` was already configured). Deprecation warnings for Recharts 2 and whatwg-encoding remain. This patch does not redesign charts, change React, or claim upstream support where the peer contract says otherwise.

## Verification after implementation

All commands ran on local macOS with synthetic data/providers stubbed, pytest auto capped at 2 and Vitest capped at 2. Targeted regressions were added and passed before dependency/workflow implementation. Compatible Node fixes passed 38 focused tests before the Vitest migration; the same 38 passed after migration.

| Command | Exit | Wall seconds | Evidence |
| --- | ---: | ---: | --- |
| `npm --prefix frontend run test -- --run tests/templates tests/components/template-dispatch.test.tsx tests/api/maintenance-fetch.test.ts tests/api/abort-signal.test.ts --maxWorkers=2` | 0 | 1.71 | 38 passed under Vitest 3.2.6 after compatible patches |
| `uv run --directory backend pytest tests/integration/test_maintenance_lifecycle.py tests/integration/test_ingest_cli.py tests/integration/test_import_activation.py -n 2 -q --no-cov` | 0 | 1.57 | 8 passed: official CLI, activation, maintenance lifecycle |
| `npm --prefix frontend run test -- --run tests/templates tests/components/template-dispatch.test.tsx tests/api/maintenance-fetch.test.ts tests/api/abort-signal.test.ts --maxWorkers=2` | 0 | 4.9 | 38 passed under Vitest 4.1.12 |
| `npm --prefix frontend ci` | 0 | 4.53 | Node 20 clean locked install; known audit findings still reported |
| `uv sync --directory backend --dev --locked --python 3.12` | 0 | 0.02 | Locked Python 3.12 install |
| `node -e 'console.log(process.version); if (process.versions.node.split(".")[0] !== "20") process.exit(1)'` | 0 | 0.02 | Node 20.20.2 assertion passed |
| `bash /tmp/tti-maintenance-evidence/smoke.sh` | 0 | 2.16 | Local macOS equivalent of workflow: 1 lifecycle + 2 MSW tests; runtime assertions; no server |
| `make build` | 0 | 4.31 | Vite 6.4.5 production build passed |
| `env -u TTI_LOCAL_AUTOSTART VITEST_MAX_WORKERS=2 make check-full` | 0 | 23.86 | 461 backend + 164 frontend tests; lint/format/types/version and all coverage gates passed |
| `bash /tmp/tti-maintenance-evidence/smoke.sh` | 0 | 1.61 | Final fixture hardening explicitly isolates shard path and disables legacy fallback; same smoke passes |

Final shard/fallback isolation hardening: `bash /tmp/tti-maintenance-evidence/smoke.sh` exit 0 in 1.61 seconds; 1 backend and 2 frontend regressions passed.

The `/tmp/tti-maintenance-evidence/smoke.sh` command is the local equivalent of the checked-in macOS workflow's runtime/smoke steps, using a fresh `mktemp` directory with `trap` cleanup. It executes the checked-in tests and is not a required repository artifact. `make check-full` includes `make check`, `make test-backend`, both module coverage checks, and full frontend coverage; no duplicate broad gate was run after success. The only subsequent test hardening isolates the shard root and turns off legacy fallback; targeted smoke/lint/format were rerun.

- Backend: **461 passed**, global **86.13%**; ingest **90.12%** (912/1012), LLM **82.05%** (1239/1510).
- Frontend: **164 passed / 27 files**; statements **84.45%**, branches **73.62%**, functions **86.74%**, lines **87.12%**. Vitest 4 uses a different V8/AST coverage remapping and denominators from Vitest 3; these percentages are recorded without treating a cross-version difference as an application coverage gain/loss. Existing global thresholds remain statements/lines/functions 80%, branches 70%, with identical source include/exclude patterns.
- `actionlint .github/workflows/ci.yml .github/workflows/audit.yml`, `pre-commit validate-config`, YAML parsing, new-test Prettier and `git diff --check`: exit 0. `gh api` verified Ruff tag v0.15.20 and the canonical hook IDs. Hook repositories were obtained with authenticated `gh repo clone`; pre-commit fetched from those local mirrors. Both Ruff hooks and all applicable commit hooks passed.
- Synthetic import asserts 40 records, 3 workouts, all 9 exact table counts, zero orphans across 6 child relations, 45.5-minute run and 90,954 steps. CLI/manifest/restarted status version IDs agree. Empty and ready status, HTTP health and gateway cleanup pass.
- Build reports the same production asset names and sizes as baseline: entry **1,377.60 / 456.41 kB gzip**, CSS **38.32 / 6.86 kB**, dashboard **172.17 / 58.26 kB**, settings **16.23 / 4.64 kB**, diagnostics **5.49 / 1.83 kB**. Existing chunk-size warning remains; it is not hidden.

## Pending checks and boundaries

Remote macOS/Ubuntu Actions are **pending actual implementation PR CI evidence**; this child does not watch or poll checks. Parent handles final integrated review, fallback browser review, #148 residual-risk acceptance, merge, post-merge checks and issue receipts. No historical or roadmap issue is closed. Quiet-machine tiny benchmark/performance baseline is explicitly deferred under the concurrent-agent instruction; no fresh `make bench` pass, throughput, browser latency or model-quality claim is made. Component tests passed, but a real browser visual review is pending the parent; there is no CSS/renderer change in this batch.

The #142 reconciliation is included by cherry-picking `1286a73f39a4ab35dc16ffe5900960708c9e1cf6` as `773ac33` (documentation only): 55 historical issues = 28 repaired / 8 residual / 19 unverified. Its 11 targeted tests are parent-supplied evidence recorded in that document, not an additional independent execution here. Historical statuses remain unchanged.
