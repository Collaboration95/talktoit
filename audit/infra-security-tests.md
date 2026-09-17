# Infrastructure, security posture, and test coverage (INF-*, TST-*)

Scope: the cross-cutting code that no single area owns — structured logging and
its redaction boundary (`backend/app/observability.py`, `backend/app/state/diagnostics.py`),
application wiring in `backend/app/main.py`, module-level caches, and the test
suites themselves. Per-area defects live in the other files; these are the parts
that only make sense viewed across the whole repository.

---

## INF-1 — the log redactor checks values, not keys, so it destroys benign identifiers and misses the leak it was written for

**Medium** — `backend/app/observability.py:59-95,113-118`; blacklist at
`backend/app/state/diagnostics.py:122-139`; tests at
`backend/tests/unit/test_observability.py:47-55`

`_redact_value` walks a structured `payload` and replaces any string that
*contains* a blacklisted token as a substring:

```python
_REDACT_VALUE_TOKENS = FORBIDDEN_CONTENT_TOKENS   # observability.py:64
```

`FORBIDDEN_CONTENT_TOKENS` is documented in its own module as the set
"used only by tests to audit the on-disk representation", and it is a list of
substrings, not secrets: `question`, `start_date`, `heart_rate`, `route`,
`gpx`, `.xml`, `record_id`, `workout_id`, `conversation_id`,
`dataset_version_id`, `SELECT `, `FROM workouts`. Applied to payload values,
the result is arbitrary:

```
{'table': 'workout_routes'} -> {'table': '[redacted]'}
{'table': 'workouts'}       -> {'table': 'workouts'}
{'metric': 'heart_rate'}    -> {'metric': '[redacted]'}
{'metric': 'step_count'}    -> {'metric': 'step_count'}
```

The documented threat model is the opposite shape. The module docstring says the
value layer guards "the place a developer could accidentally pass a question or
a route row"; a question passed under its natural key is what the check misses,
because only value text is inspected:

```
{'question': 'how many runs last week'}   -> unchanged
{'meta': {'sql_text': 'how many runs'}}   -> unchanged
```

**Impact.** Ingest and reconcile telemetry loses the identifiers that make it
useful — table names, route/GPX stages, metric names — while the most likely
accidental leak (a value entered under a sensitive key) is written to stderr
unredacted. `DiagnosticsRepository.record` already rejects
`FORBIDDEN_META_KEYS` keys at the store boundary, so the log path is the weaker
of the two.

The suite cannot see either half: the tests assert that every forbidden token is
scrubbed at least once (`test_observability.py:55` counts `[redacted]`
occurrences and only requires `>= len(tokens)`), which over-redaction makes
easier to satisfy.

**Fix.** Separate the two purposes. Validate payload *keys* against
`FORBIDDEN_META_KEYS` (drop or reject unknown keys, as the diagnostics store
does) and reduce value redaction to secret-shaped patterns: bearer tokens,
`api_key=`, absolute paths, SQL keywords. Test both directions — secrets
scrubbed and `{'table': 'workout_routes'}` intact.

---

## INF-2 — startup and HTTP surface hardening

**Low** — `backend/app/main.py:31,191-199,215-227`

Cross-referenced from API-14, and repeated here because the items belong to the
process rather than to a feature:

- The CORS allowlist is the single literal `http://localhost:5173` with
  `allow_credentials=True`; any other dev port or LAN address must edit the
  source. It is a deliberate local-first default, not a hole, but it is the only
  configuration knob that requires a code change.
- The SPA is mounted at import time based on `frontend/dist` existing, and the
  catch-all `@app.get("/{full_path:path}")` is registered after the API routers. With
  `dist/` present (it is, in this working tree), any unmatched `GET /api/...` path
  falls through to the SPA and returns `index.html` with status 200 instead of a
  JSON 404, so a frontend typo or a removed route shows up as an HTML parse
  error rather than a clear 404.

  ```
  $ ./backend/.venv/bin/python audit/repro/tti_spa_404.py
  GET /api/definitely-not-a-route -> 200 text/html; charset=utf-8
  body starts with: <!DOCTYPE html> <html lang="en">   <head
  ```
- `APP_VERSION = "0.1.0"` is a literal used both for the app object and the
  startup telemetry, so the reported version cannot be traced to a build.
- FastAPI's `/docs`, `/redoc` and `/openapi.json` stay enabled; for a local app
  that is convenient, and it is worth an explicit decision because the default
  becomes a surface the day the app is bound to a non-loopback interface.

**Fix.** Keep the defaults, but put the origin list behind an env var, return a
JSON 404 for `/api/*` before the catch-all, take the version from package
metadata, and decide whether the docs endpoints ship in the built app.

---

## INF-3 — the dashboard capability cache is a mutable process global

**Low** — `backend/app/db/dashboard_cache.py:49-78`; cross-ref API-11

The cache is a module-level structure behind a single `threading.Lock`, handed
out by reference to request handlers, so two threads can hold the same entry and
mutate it (API-11 describes the concrete eviction bug that follows). It is
in-process only, so `--workers 2` would give each worker its own copy and its
own invalidation timing; nothing in the code or docs says that must not happen.
Keeping the note here because the fix (return a copy, or key the cache by
dataset version and give the CLI/server each one) is a boundary decision rather
than a line-level bug.

---

## INF-4 — no in-code defect markers, and 21 comments point at work items a reader cannot resolve

**Low** — `backend/app`, `frontend/src`, `scripts` (verified with a repository-wide
search for `TODO`/`FIXME`/`XXX`/`HACK`)

There are zero such markers, which is unusual and mostly good: the repository has
kept its known-issues list in `AUDIT.md`, `issues/` and GitHub instead of in
comments. The cost is that a comment citing a work item is now the only place
some context lives — and 21 references across `backend/app` and `frontend/src`
cite IDs that do not resolve in the repository:

```
R1-01 ×6, R1-12 ×4, GH-42 ×3, R1-11, R1-09, R1-04, GH-3, GH-44, GH-45, GH-47
```

The in-repo tracker uses different schemes (`A-01`…`A-16` in `AUDIT.md`,
`gh-01`…`gh-22` in `issues/`), and neither `AUDIT.md` nor `docs/ENGINEERING.md`
defines the `R1-`/`GH-` namespaces, so a new reader cannot tell whether
`GH-47` (`frontend/src/components/chat-view.tsx:23`, the degraded-answer notice)
is open, fixed, or abandoned.

**Fix.** Either drop the IDs in favour of a sentence describing the invariant,
or add a short `docs/WORK_ITEMS.md` mapping each namespace to its tracker.

---

## TST-1 — ingestion tests assert row counts, never values, so ING-1 hides behind a green suite

**High** — `backend/tests/integration/test_ingest_v2.py:27-48`,
`backend/tests/integration/test_worker_invariance.py:23-84` and `:87-117`

Every V2 assertion is a count:

```python
assert stats["records"] == 40
assert stats["workouts"] == 3
```

The cross-worker consistency test goes one step further and compares
`records.value` sets between 1 and 4 workers, but selects neither
`activity_type` nor any workout column, so the ING-1 defect (every workout
`activity_type` empty in the V2 path) is invisible to it — all four worker
counts agree, and all four are wrong in the same way. The same is true of the
duration-unit defect: no fixture row mixes `hr` and `min` (TST-5), so no
assertion could fail.

**Evidence.** `audit/repro/tti_v2_e2e.py` shows the counts matching the legacy
path exactly while `SELECT DISTINCT activity_type FROM workouts` returns
`[('',)]`.

**Fix.** Add value-level assertions for each table the V2 path writes
(`activity_type`, `duration`/`duration_unit`, route point counts, HRV beat
counts), and extend the worker-invariance comparison to the workout tables.

---

## TST-2 — most integration tests seed through the legacy parser, so the default ingest path is never the one under test

**High** — `backend/tests/integration/test_ingest.py:14`,
`backend/tests/integration/test_dashboard_contracts.py:19`,
`backend/tests/integration/test_queries.py:22`,
`backend/tests/integration/test_chat.py:19` and nine more files

`from app.ingest.parser import ingest` appears in thirteen test modules; only
`test_ingest_v2.py`, `test_worker_invariance.py`, `test_ingest_compatibility.py`
and `test_typed_record_values.py` exercise the coordinator that
`make ingest` actually runs. Everything that tests query results, dashboard
contracts, chat answers, caching and the API is built on data the legacy parser
produced.

**Impact.** The two parsers can disagree — and ING-1 is exactly such a
disagreement — while every downstream test stays green, because the downstream
tests never see the V2 output. The dashboard/chat suites would need new
assertions, not just new fixtures, to catch a V2 regression.

**Fix.** Convert the shared fixture helper to `ingest_v2` (or parameterize it)
so the default path is what the contract tests exercise, and keep one explicit
legacy-parser suite for compatibility.

---

## TST-3 — nothing invokes the ingest CLI

**Medium** — `backend/tests/` (no test imports `app.ingest.run`)

`rg 'run\.main|from app\.ingest import run' backend/tests` returns nothing, so
the argument parser behind `make ingest` — including the `--workers` flag that
ING-2 shows is parsed incorrectly — has no test at all. The CLI's JSON report
format is covered indirectly by `test_ingest_dry_run.py`, which calls the
functions the CLI calls rather than the CLI.

**Fix.** Add a subprocess or `capsys` test that runs the module with
`["export.xml", "--workers", "2"]` against the fixture and asserts the parsed
worker count and the exit status.

---

## TST-4 — the CLI environment variable path is untested for non-numeric values

**Medium** — `backend/tests/unit/test_worker_policy.py:14-27`;
`TTI_INGEST_WORKERS` handling in `backend/app/ingest/run.py`

`test_worker_policy.py` covers `resolve_worker_count` with `auto` and
`not-a-number`, which is why the resolver looks correct in isolation. ING-3 is
a failure in the *logging line* that consumes the resolved value, so it only
appears when the CLI runs with the env var set. No test does that.

**Fix.** One CLI-level test with `monkeypatch.setenv("TTI_INGEST_WORKERS", "auto")` and
one with `"not-a-number"` asserting the process logs and exits 0.

---

## TST-5 — the fixture has no mixed-unit data, so the unit-summing defects cannot fail a test

**Medium** — `backend/tests/fixtures/sample.xml` (energy is kJ-only, for example
`:126-130` and `:180`)

Every `ActiveEnergyBurned` row uses `unit="kJ"` and no workout mixes `hr` and
`min` durations, so QRY-1 (duration sums) and QRY-2 (energy sums) are both
invisible to the suite: with one unit present, summing raw numbers happens to be
correct. The repro scripts in `audit/repro/tti_units.py` construct the mixed case
by hand.

**Fix.** Add a small synthetic export (or extra fixture rows) with one `hr`
workout, one `min` workout, one kJ energy row and one kcal row in the same
period, and assert the totals convert.

---

## TST-6 — no test covers cache poisoning or cross-conversation cache isolation

**Medium** — `backend/tests/integration/` (chat cache suite at
`backend/tests/unit/test_chat_cache.py` covers capacity, byte budget and
dataset scoping only)

API-1 (a provider-unavailable fallback cached as a successful answer) and API-2
(a disambiguation prompt replayed into another conversation) are both
cache-key issues, and neither shape appears in the existing cache tests. The
repro scripts `audit/repro/tti_fallback_cache.py` and
`audit/repro/tti_disamb_cache.py` are the missing coverage written out by hand:
they show `cache_hit=True` and `provenance='cached'` on the second
request, with the disambiguation text returned identically in a conversation it
was never asked in.

**Fix.** Promote both scripts into `backend/tests/integration/test_chat_cache_isolation.py`,
asserting that degraded envelopes are not stored and that a plan needing
clarification is keyed by conversation.

---

## TST-7 — nothing asserts the two sleep panels agree

**Low** — `backend/tests/integration/test_dashboard_profile_cache.py:34-35`,
`backend/tests/integration/test_concurrency.py:34-35`

Both `/api/dashboard/sleep` and `/api/dashboard/sleep/stages` are requested in
those suites, but only for status codes and cache behavior.
`backend/tests/unit/test_sleep_stages.py` tests the interval-union helper with
hand-built rows and never compares the two endpoints on the same data, which is
what API-3 (different source filters, so the panels disagree) would need.

**Fix.** Add one integration test that ingests a fixture with an `AutoSleep` row
and asserts the daily total and the stages total are consistent.

---

## Strengths worth keeping

- `.github/workflows/ci.yml` (86 lines) runs version consistency, Ruff lint and
  format checks, Pyright, pytest with the global 80% gate, then
  `coverage report --include="app/ingest/*" --fail-under=90` and
  `--include="app/llm/*" --fail-under=70`, and finally frontend lint, typecheck,
  tests and build. The per-module gates are what make the coverage number mean
  something.
- `.github/workflows/audit.yml` runs `pip-audit` and
  `npm audit --audit-level=moderate` weekly (Mondays 08:00 UTC), which is more
  than most repositories of this size do.
- `backend/tests/integration/test_worker_invariance.py` genuinely runs the
  coordinator at 1, 2, 4 and 6 workers on a shared fixture, so worker-invariance
  claims are backed by execution rather than one code path.
- The redaction tests that do exist
  (`backend/tests/unit/test_provider_redaction.py`,
  `test_observability.py`) at least pin the direction of travel, and the
  diagnostics store's key allowlist is enforced with `pytest.raises`.
