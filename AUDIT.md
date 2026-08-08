# tti Architectural Audit — Triage Tracker

Audit date: 2026-08-07. Branch audited: `audit/fixes` (at merge `f9e6612`, == `main`).
Read-only review. No source/package files were modified. Working tree had a
pre-existing uncommitted `.gitignore` change (adds `.pi/`) and an untracked
`audit-1/` directory from a prior (July 2026) review; both recorded below.

Ground truth used: committed `AGENTS.md`, `README.md`, `docs/*`, `Makefile`,
`backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/*`,
`.pre-commit-config.yaml`, and the checked-in source.

Guideline respected: the repo already enforces a strong baseline (Ruff, Pyright
strict-minus-5, Prettier, oxlint, pytest global 80% + per-module ingest 90%/llm
70%, Vitest thresholds 80/80/80/70, `pip-audit` + `npm audit` weekly, pre-commit,
headless `verify-headless`). Findings below target **gaps beyond** that baseline;
baseline tools present are not re-proposed.

---

## Summary table

| ID | Category | Finding (one line) | Severity | Effort | GH# | Quick? |
|----|----------|--------------------|----------|--------|-----|--------|
| A-01 | Performance | `get_data_profile` full-table scan recomputed 2× per chat request and 2× per dashboard endpoint (≈12–14 scans per dashboard load) | High | M | 14 |
| A-02 | Concurrency | `async` chat handler runs all DuckDB + SQLite work synchronously on the event loop | High | M | 15 |
| A-03 | Performance | Every `AppStateRepository` accessor re-runs `migrate()` and opens 2 SQLite connections on the hot path | Medium | S | 16 |
| A-04 | Observability | `diagnostics_events` has no retention; `aggregate()` loads the whole table into memory | Medium | S | 17 |
| A-05 | Performance | `get_top_workouts` fetches+Python-sorts all rows (incl. distance subquery over full stats) and `comparison` issues 6 aggregates | Medium | M | 18 |
| A-06 | Performance | `semantic_turns()` loads full `response_json` for all turns per request; cache lookup after heavy profile work | Medium | M | 19 |
| A-09 | Concurrency | Shared SQLite app-state, default journal/`busy` settings, concurrent panel writers | Medium | M | 20 |
| A-14 | Docs | `ENGINEERING.md` stale: per-module gates now enforced in CI (doc says “goals, tracked manually”); pre-commit `no-commit-to-branch` documented but absent; `docs/DISCOVERY.md` referenced but does not exist | Medium | S | 21 |
| A-12 | Observability | No structured logging; raw-string `logger.info` on hot paths (incl. glyph `\u2713`) | Low | M | 22 |
| A-10 | Testing/code | Production `chat-view` branches on `navigator.userAgent.includes('jsdom')`; duplicated 3s health-check effect in 2 views | Low | S | 23 |
| A-11 | Frontend UX | Tab switch uses `pushState` without a `popstate`/back handler | Low | S | 24 |
| A-13 | Correctness | `main.py` startup telemetry hardcodes `app_state_version: "7"` while the store now migrates to v8 | Low | S | 25 |
| A-07 | Performance | `format.ts` builds a new `Intl.*Format` per call/bucket (no memo) | Low | S | 26 |
| A-15 | Hygiene | `audit-1/` untracked; `.gitignore` still modified in working tree | Low | S | 35 |
| A-16 | Packaging | No CHANGELOG/version-bump policy or backend distributable build; FE-only build verified in CI | Low | M | 27 |
| T-01 | Testing | No concurrency/integration test for parallel chat+dashboard against shared SQLite (A-09/A-03) | Medium | M | 28 |
| T-02 | Testing | No test asserting startup schema-version telemetry (would have caught A-13) | Low | S | 29 |
| T-03 | Testing | Formatting label / formatter-perf coverage for `formatBucketLabel`, year-boundary weeks | Low | S | 30 |
| T-04 | Testing | No test exercising `#  AbortController` path that the `jsdom` branch suppresses (A-10) | Low | M | 31 |
| T-05 | Testing | Cache-revalidation test for the A-01 profile cache; keep `benchmark` marker out of default run | Low | S | 32 |
| L-01 | Tooling | Add structured logging (structlog) as an enhancement issue — not enabled today | Low | M | 33 |
| L-02 | Tooling/release | Add CHANGELOG + version-consistency check + optional frontend artifact verification in CI | Low | M | 34 |

### Local ID → GitHub issue map

| Local | GH# | Local | GH# | Local | GH# |
|-------|-----|-------|-----|-------|-----|
| A-01 | 14 | A-10 | 23 | T-03 | 30 |
| A-02 | 15 | A-11 | 24 | T-04 | 31 |
| A-03 | 16 | A-13 | 25 | T-05 | 32 |
| A-04 | 17 | A-07 (format) | 26 | L-01 | 33 |
| A-05 | 18 | A-15 | 35 | L-02 | 34 |
| A-06 | 19 | A-16 | 27 | | |
| A-09 | 20 | T-01 | 28 | | |
| A-14 | 21 | T-02 | 29 | | |

> Issue files are drafted under `issues/` (one per GH#), ready to paste into the
> repo's GitHub tracker. Priorities re-use repo-style labels: `performance`,
> `concurrency`, `observability`, `testing`, `infrastructure`, `devtooling`, `docs`,
> `bug`; severity high/medium/low.

## Repository map (verified, not from docs alone)

- `backend/app/main.py` — FastAPI factory; lifespan builds provider gateway, runs
  `migrate()` (DuckDB) + `AppStateRepository().migrate()` (SQLite), records startup.
  Serves built frontend from `frontend/dist` when present.
- `backend/app/api/` — thin routers: `chat`, `conversations`, `dashboard`,
  `status`, `saved_views`, `diagnostics`, `settings`. Dashboard handlers are sync
  `def` (threadpructured by FastAPI); `chat` is the only `async` handler w/ big Dio work.
- `backend/app/db/` — `connection` (open/close per request), `schema` (DROP+CREATE,
  called at ingest load), `migrate` (in‑place DuckDB ALTER for pre-existing DBs),
  `data_profile` (full-table scans → `DataProfile`), `queries` (typed query fns),
  `aggregations` (bucket math), `migrations` none.
- `backend/app/analytics/` — `metric_catalog`, `registry` (typed QueryRegistry +
  exec adapters shared by chat tools + dashboard).
- `backend/app/llm/` — `orchestrator` (shared `ChatOrchestrator` used by CLI+HTTP),
  `local_planner`, `tools` (JSON schemas + dispatch), `provider_gateway` (bounded
  retry/circuit breaker), `provider_projection` (redaction), `semantic_candidates`,
  `followups`, `cache_keys`, `client`.
- `backend/app/ingest/` — V2: `run` → `coordinator` (mmap split + `ProcessPool`) →
  `bytescan` (workers) → `reconcile` (Parquet → DuckDB with global-ID FK rewrites),
  `compatibility`/`require_well_formed_export` gates; `--legacy` → `parser`. Release
  critical by policy.
- `backend/app/state/` — `app_state` (SQLite: dataset versions, conversations,
  turns, cache, saved views; `CACHE_MAX_ENTRIES/MAX_BYTES` eviction) +
  `diagnostics` (privacy-allowlisted events).
- `backend/app/cli/` — `chat` (REPL on same `ChatOrchestrator`), `diagnostics`,
  `status`.
- `frontend/src/` — `api/` typed fetch clients, `components/` (views),
  `templates/` (per `template_id`) + `TemplateDispatch` fallback, `charts/`,
  `lib/format.ts` & `dashboard-query.ts`, `types/`, `app.tsx`.
- Tests — `backend/tests/{unit,integration,bench}`; `frontend/tests/{api,components,
  templates,lib}`.

## Findings by category

### Performance (A-01, A-03, A-04, A-05, A-06, A-07)
- **A-01 (high)** `get_data_profile` runs 3 heavy scans per call (`_SQL_COVERAGE`
  MIN/MAX over records+workouts+activity_summaries, `_SQL_WORKOUT_TYPES` GROUP BY
  all workouts, `_SQL_AVAILABLE_METRICS` DISTINCT over records). `_resource_metadata`
  and `_resolve_window` each call it, so every dashboard endpoint does it twice
  (6 panels → ~12 full scans); chat endpoint (chat.py:100) does it and then
  `orchestrator.answer` does it again (orchestrator.py:210). Additionally
  `resolve_activity_type` re-runs `_SQL_WORKOUT_TYPES` for each chat tool. On a
  ~137 MB DuckDB this dominates request latency and repeats identical *deterministic*
  results. Fix: cache `DataProfile` keyed by dataset version id / `content_hash_prefix`
  and revalidate only on activation (issue-01).
- **A-03 (med)** `AppStateRepository` — every accessor calls
  `self.migrate()` (which itself opens a connection + PRAGMA) then opens a second
  connection. A single chat request churns ~8–10 accessor calls ≈ 16+ SQLite
  connect/close and repeated `CREATE TABLE IF NOT EXISTS`-class DDL checks.
- **A-04 (med)** `diagnostics_events` grows without a retention/eviction policy on
  a long-lived local app; `aggregate()` `SELECT *`s the whole table into memory.
- **A-05 (med)** `get_top_workouts` executes `_SQL_TOP_WORKOUTS` with **no LIMIT**,
  joins the whole `workout_statistics` distance subquery, returns every matching row,
  then sorts in Python and truncates to `n`. `get_comparison` = 6 aggregate queries;
  `get_period_summary` = 3. All could push `ORDER BY/LIMIT` into SQL and coalesce
  metric aggregates.
- **A-06 (med)** `semantic_turns()` selects `response_json` for every completed turn
  and loads it all in memory per request to match one; exact-cache lookup happens
  only **after** `get_data_profile` + `plan_local_question` (a pure cache hit still
  pays the profile scan).
- **A-07 (low)** `frontend/src/lib/format.ts` constructs `Intl.NumberFormat`/
  `DateTimeFormat` per call; invoked per point in chart label loops.

### Concurrency & resource-correctness (A-02, A-09)
- **A-02 (high)** `POST /api/chat` is `async def` but performs all DuckDB
  (`get_data_profile`, tool `dispatch_tool`), SQLite (repository reads/writes), and
  diagnostics writes synchronously on the event loop; only the provider gateway call
  is awaited. A slow query on the 137 MB DB blocks the whole loop. Recommend wrapping
  the local DB/state work in `run_in_threadpool`/`to_thread`, or making the handler
  sync and keeping the await via the gateway — verify CLI path unaffected.
- **A-09 (med)** All SQLite access (app_state + diagnostics) shares one file with
  default `sqlite3.connect` (no `WAL`, no `busy_timeout`). The dashboard fires 8
  parallel requests whose `def` handlers run in the threadpool and all call
  `safe_record` (writer) + `get_active`; concurrent writers on a non-WAL DB risk
  `database is locked` and added latency. Recommend `journal_mode=WAL`,
  `busy_timeout`, and serializing diagnostics writes.

### Observability & privacy (A-04, A-12, A-13)
- The **diagnostics privacy allowlist** (`FORBIDDEN_META_KEYS`, per-category allowed
  keys, token blacklist) is a clear strength and passes tests. Nothing sensitive leaks
  (verified in `state/diagnostics.py`). Not a finding — recorded as strength.
- **A-12 (low)** Backend uses stdlib `logging` with raw strings and mysql `\u2713`
  glyphs in `reconcile/coordinator`; no structured logs. Enhancement (L-01).
- **A-13 (low)** `main.py` records `"app_state_version": "7"` hardcoded; the store
  now migrates to `user_version=8` — startup telemetry mislabels the live schema.

### Concurrency/backpressure (in provider) — PASS
`provider_gateway.py` is a model: bounded semaphore, deadline, fixed retries,
circuit breaker, cancellation-safe. No finding.

### Documentation accuracy (A-14)
`docs/ENGINEERING.md` is stale and now contradicts the running tree:
1. §2.4 says ingest 90% / llm 70% are *goals, tracked manually, not enforced* and
   gives a "if we later want these enforced" snippet — but `ci.yml` (#test-backend)
   and `make check-full` now run exactly those `coverage report --fail-under` gates.
   The committed doc describes the OLD state.
2. §6 lists a pre-commit `no-commit-to-branch` hook (blocks direct pushes to `main`);
   the committed `.pre-commit-config.yaml` does **not** contain it.
3. §1 + the committed `docs/planning/README.md` point to `docs/DISCOVERY.md` as the
   source-of-truth decisions log, but that file is absent from the tree and from git
   (only `ENGINEERING`, `HEALTH_DATA_UI_STYLEGUIDE`, `LLM_CLI_AND_TOOL_RESILIENCE_PLAN`,
   `SPEC`, `planning/README` exist).
4. §4 `Makefile` walk-through omits the now-present targets (`check`, `check-full`,
   `run-cli`, `groq-smoke`, `status`, `diagnostics`, `bench`, `verify-headless`,
   `test-bk/test-fe`).
Per the audit rule, the committed working references are ground truth and the
stale doc is itself the finding.

### Testing health (baseline strong; gaps T-01..T-05, A-10)
- Baseline is strong: small synthetic fixture, `tmp_path`/in-memory DuckDB,
  unit/integration split, worker-invariance + ingest-contract tests, benchmarks,
  `verify-headless`, coverage ceilings in CI.
- **T-01**: No test emits multiple concurrent chat+dashboard requests against the
  shared SQLite state to exercise A-02/A-09 (lock contention or event-loop
  serialization). Add as async integration test with a `TaskGroup`.
- **T-02**: No assertion on the startup event's `app_state_version`, so A-13 slipped.
- **T-04**: no test drives the AbortController signal path that the `jsdom` branch
  masks.
- **T-05**: when introducing the A-01 profile cache, add a revalidation test (bump a
  fake dataset and assert the profile refreshes) and keep the `benchmark` marker out
  of the default `pytest` addopts (today `pytest -n auto` runs benchmarks in CI).

## Testing proposal (mapped back to IDs)
1. **Split benchmark marker out of the default suite** (`addopts` … `-m "not benchmark"`)
   so CI time isn’t padded; keep a separate `test-bench` job/`make check-full` step.
   → `T-05`, `A-05`.
2. **Add a concurrency integration test** (chat + 2 dashboard requests via the
   `TestClient`, or TaskGroup-to-the-gateway) that asserts no `database is locked`,
   no interleaved async-suspend corruption. → `T-01`, `A-02`, `A-09`.
3. **Add a profile-cache unit test + a startup-telemetry contract test** (assert
   `app_state_version` equals the max `PRAGMA user_version`). → `T-02`, `T-05`,
   `A-01`, `A-13`.
4. **Frontend**: remove the `jsdom` branch and add an MSW-based test that exercises
   the real `AbortController` (cancel) path; extend `format.ts` tests for
   year-boundary ISO week buckets and that formatters accept sparse series. → `T-03`,
   `T-04`, `A-10`, `A-07(6)`.

## Tooling & release proposal (mapped)
1. **Structured logging (enhancement)** — adopt `structlog` (or JSON formatter) for
   backend, with request/event context, keeping the diagnostics allowlist as the only
   on-disk telemetry. → `L-01`.
2. **Release/versioning hygiene (enhancement)** — add a root `CHANGELOG.md`, a CI
   assertion that `pyproject.toml` / `package.json` / `main.APP_VERSION` agree, and an
   optional `make dist` that builds+tar the frontend bundle and records a git tag in
   a `Version` audit. Note: this is a local app — no signing/attestation is claimed;
   the checklist row is honest `n/a` rather than fake. → `L-02`, `A-16`.
3. **No new linter/typechecker proposed** — Ruff, Pyright, oxlint, Prettier are
   present and CI-enforced; adding `mypy` or Biome would duplicate existing gates.

## Non-goals / deliberately out-of-scope, with reason
- **Sending raw health records / GPS to the LLM** — already prohibited by
  architecture (projections/allowlists). Excluded as a strength, not a finding.
- **Multi-user / auth / cloud sync / SaaS** — the product is explicitly local-first,
  single-user, no-account. Out of design scope.
- **License/entitlement/sandbox signing** — cross on macOS a local web app has no
  bundled binary release; shipping/signing is a declared non-goal until a packaged
  desktop target exists.
- **Rewriting the V2 ingest pipeline** — it is well-built and release-critical;
  audit only notes the per-table `SELECT COUNT(*)` inside the load transaction loop
  (logging side-effect) as an optional cleanup, not a redesign.
- **Adopting a chart library other than the committed ECharts/Chart.js/Tremor set** —
  that is a product decision governed by the HEALTH_DATA_UI_STYLEGUIDE, not an audit.
- **Browser back-button/URL router framework** (React Router) — out of scope; a
  `popstate`-listener (A-11) suffices.

## Composition
- Must fix before calling 1.0 hardening "done": **A-01, A-02, A-04**, plus **A-14** and
  **A-13** because the working-reference docs and telemetry mis-state reality; and
  **T-01** to prove the concurrency fixes.
- The repo is in a healthy, well-gated state overall; the dominant theme is
  redundant/deterministic work being repeated (profile scans, per-call `migrate`,
  unbounded diagnostics) and an async handler that blocks, rather than design-level
  defects in either pipeline or reactors.

Every item in this tracker has a matching issue draft under `issues/`.
