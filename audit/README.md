# tti code audit — September 2026

A line-by-line review of every file in this repository that executes: the Python
package under `backend/app`, the React/Vite sources under `frontend/src`, the
scripts under `scripts/`, and the Makefile and CI workflows that drive them.
Documentation, fixtures, and generated data were read for context but are not
audited as code.

The review is read-only. Nothing in `backend/` or `frontend/` was changed;
this `audit/` directory is the only new content, and it is untracked so the
working tree stays clean. Every finding below was reproduced against the code at
`d060481` before it was written down, and the scripts that reproduce them ship
in `audit/repro/`.

## How to read this

Each finding has a stable ID (`ING-1`, `QRY-1`, `API-1`, `LLM-1`,
`FE-1`, `INF-1`, `TST-1`), a severity, a file and line anchor, a
description, the impact on a user, a suggested fix, and the evidence that made it
concrete. IDs are grouped by area into one file each:

| File | IDs | Area |
| --- | --- | --- |
| `backend-ingest.md` | ING-1 … ING-9 | XML ingestion, V2 byte scan, CLI entry point, reconciliation |
| `backend-db-queries.md` | QRY-1 … QRY-7 | Schema, aggregations, query functions, analytics registry |
| `backend-api-state.md` | API-1 … API-16 | FastAPI routes, chat orchestrator boundary, app state, caches |
| `backend-llm.md` | LLM-1 … LLM-9 | Local planner, follow-ups, tools, provider gateway, LiteRT control |
| `frontend.md` | FE-1 … FE-12 | React components, API clients, formatting helpers |
| `infra-security-tests.md` | INF-1 … INF-4, TST-1 … TST-7 | Cross-cutting hardening, observability, test coverage |
| `repro/` | — | Runnable scripts behind the evidence lines |
| `github-issues.md` | — | Issue number for every finding, and how the new items relate to the earlier A-/GH- set |

Severity is about user-visible consequence, not code tidiness:

- **Critical** — silently corrupts the data the whole app is built on, in the default path.
- **High** — wrong numbers, wrong answers, or a crash in a documented workflow.
- **Medium** — incorrect behavior in a narrower case, cross-request leakage, event-loop stalls, or a real resource bug.
- **Low** — hardening, dead code, misleading telemetry, duplication, hygiene.

## What matters most

1. **ING-1 (Critical).** The default V2 ingest writes an empty `activity_type`
   for every workout, because `bytescan.py` reads an attribute name that never
   exists. Every workout in a freshly imported database is untyped.
2. **QRY-1, QRY-2 (High, Medium).** Workout duration and energy are summed as
   raw numbers with their units ignored, so a period that mixes `hr` and
   `min` rows produces a meaningless total, and kJ and kcal rows are added
   together as if they were the same.
3. **ING-2, ING-3 (High).** Two documented CLI/configuration forms abort the
   importer: `export.xml --workers 2` reports `File not found: 1`, and
   `TTI_INGEST_WORKERS=auto` raises `ValueError` from a logging line after
   the real worker count has already been resolved correctly.
4. **API-1, API-2 (High).** Degraded and context-dependent answers are written to
   the response cache. A "the provider is unavailable" fallback is replayed as a
   successful cached answer forever, and a follow-up disambiguation question
   asked in one conversation is replayed verbatim in every other conversation.
5. **API-3 (Medium).** The two sleep panels disagree, because one filters out
   `AutoSleep` rows and the other does not.
6. **API-4 (Medium).** `POST /settings/llm/start` awaits an 8-second blocking
   poll on the event loop; the repro measures an 8.34 s stall during which the
   whole API is unresponsive.
7. **API-16 (Medium).** The routes that skip `Depends(get_app_state_repository)`
   migrate the state store once per repository instance. Two processes opening a
   fresh store can collide (`database is locked`, `table conversations already exists`), and
   every read-only request pays a connection and a version check the shared
   dependencies were introduced to remove.

## Prior audits and their status

This repository already had two review passes: `AUDIT.md` (findings A-01 …
A-16, tracked as GitHub issues #14–#35) and the superseded planning tree in
`audit-1/`, with the issue drafts in `issues/`. This audit does not restate
those findings, and where it touches adjacent code it records whether the older
issue is still open:

| Prior item | Status now |
| --- | --- |
| A-01 — duplicate data-profile scans in dashboard handlers | **Fixed.** All dashboard handlers route through `resolve_dashboard_context` in `backend/app/api/dashboard.py`. The only residual duplicate scan is in the chat path, reported as API-8. |
| A-05 — `get_top_workouts` limited before Python-side filtering | **Stale, not reproducible.** The current query ranks in SQL and filters afterwards correctly (`backend/app/db/queries.py:544-547`); checked with `audit/repro/tti_topn.py`. |
| A-10 — jsdom branch shipped in production code | **Fixed.** No `userAgent`/`jsdom` branching remains in `frontend/src`. |
| A-13 — startup telemetry reported the wrong schema version | **Fixed.** `backend/app/main.py:151` records `APP_STATE_SCHEMA_VERSION`. |
| A-01 adjacent — one repository per request | **Partly regressed.** `app/api/deps.py` exists to share the lifespan instances, but the status, saved-view, conversation, diagnostics, and settings routes still build their own; reported as API-16. |

## Strengths worth keeping

The review found no defects in these areas, which matters when deciding where to
spend review attention:

- **Workout keyset pagination is correct.** The `(start_date, id)` tuple
  comparison in `_SQL_WORKOUTS_PAGE` is a proper total order, and the cursor
  survives duplicate timestamps (`audit/repro/tti_page_check.py`).
- **Worker-invariance is real.** V2 shard counts agree exactly across 1, 2, 4,
  and 6 workers for every table, including child rows.
- **CI is stronger than most projects this size.** `.github/workflows/ci.yml`
  runs lint, format, typecheck, and tests with per-module coverage gates (80%
  global, 90% ingestion, 70% LLM), and `audit.yml` runs `pip-audit` and
  `npm audit` weekly.
- **Privacy boundaries are deliberate and mostly held.** Raw records and GPS
  geometry are never sent to the narrative model; the fallback envelope never
  leaks prompts, SQL, or stack traces; diagnostics have a token blacklist that is
  actually tested.
- **The chat path keeps one orchestrator.** CLI and HTTP answers run through the
  same `ChatOrchestrator`, so the two surfaces cannot drift.

## Reproducing

Run the scripts from the repository root; they insert `backend` on
`sys.path` and use the synthetic fixture `backend/tests/fixtures/sample.xml`,
never real health data:

```bash
./backend/.venv/bin/python audit/repro/tti_v2_e2e.py
```

Two environment notes apply to `app.ingest.run`, and both look like tooling
problems rather than product bugs: the module is importable as `app.*` only
from the `backend/` directory, and `make ingest` fails in a sandboxed shell
because `uv` cannot write its cache metadata. Neither affects the findings.

## What this audit did not cover

- **No live remote provider calls.** Everything touching Groq or LiteRT was read
  and exercised with fakes; latency, retry, and quota behavior against the real
  service was not measured.
- **No real Apple Health export.** The V2 findings use the synthetic fixture. A
  real `export.xml` would add value to ING-4 in particular, because the fixture
  differs from real exports in exactly the way that hides that bug.
- **No browser-based UI testing.** Frontend findings are from code reading and
  the existing Vitest suite; no Playwright run was performed.
- **No timing or memory profiling** beyond the specific event-loop repro in
  `audit/repro/tti_eventloop.py`.
