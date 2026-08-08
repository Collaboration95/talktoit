# Testing Proposal — tti (mapped to backlog IDs)

Complements the existing strong baseline (synthetic fixtures, `tmp_path`,
unit/integration split, worker-invariance, ingest-contract, benchmarks,
`verify-headless`, global + per-module coverage gates). Each gap → its own issue.

## Layout & grouping (fast + parallel)
The suite is already well grouped (`backend/tests/unit|integration|bench`,
`frontend/tests/api|components|templates|lib`). Add:

1. **Concurrency integration** — `backend/tests/integration/test_concurrency.py`
   (new). Uses `TaskGroup` + a `tmp_path` store + synthetic fixture to drive 2–3
   chat and the 8 dashboard panel requests concurrently; asserts no
   `database is locked`, no 500s, correct dataset scoping/caches. → **GH-16**.
2. **Startup lifecycle contract** — assert the lifespan startup event records
   `app_state_version` equal to the store's max `PRAGMA user_version` and that the
   event passes the diagnostics allowlist. → **GH-17** (catches GH-12).
3. **Profile-cache unit test** — flips a fake dataset id and asserts the A-01
   `DataProfile` cache refreshes on activation and is served otherwise. →
   **GH-20** (with GH-01).
4. **Benchmark marker separation** — default `pytest` excludes `benchmark` via
   `-m "not benchmark"` so CI stays fast; `make test-bench`/separate CI job runs
   them explicitly. → **GH-20**.

## Frontend
5. **Abort/cancel path** — remove the `jsdom` user-agent branch (GH-10) and add an
   MSW-based test that delays `/api/chat`, aborts, and asserts the turn shows the
   cancelled-error state. → **GH-19**.
6. **Formatting helpers** — add year-boundary ISO-week cases and sparse-series
   cases; assert formatters return `None`/fallback without throwing across
   day/week/month. → **GH-18**. Memoize formatters (GH-13) and re-run existing
   `format.test.ts` unchanged.

## Type-checking / lint
Already strong: Pyright strict-minus-5 (documented relaxations for DuckDB/lxml),
Ruff, oxlint, Prettier; all CI-enforced + pre-commit. No new tool proposed (adding
`mypy`/Biome would duplicate existing gates). Revisit Pyright rule relaxations
progressively per ENGINEERING §9.10.

## TypeScript implement type-checking gap note
The frontend `tsconfig` strict flags (`noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`) are already exercised by template payloads. No
change.

## Suite performance
- Ensure the `benchmark` marker never runs in the default suite (today `pytest`
  with `-n auto` runs it).
- Consider `--dist loadscope` partitioning for the integration suite if it grows.

## Coverage notes
Keep the existing gates (global 80%, ingest 90%, llm 70%, FE 80/80/80/70). Add
the new concurrency/lifecycle paths to `--cov` automatically (they live under
`app/`), and confirm the diagnostics allowlist tests remain the privacy boundary
that must not loosen.
