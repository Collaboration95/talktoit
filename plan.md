# tti audit remediation plan

## What this is

Every finding from the September 2026 audit in `audit/` is tracked as one GitHub
issue in `Collaboration95/talktoit`. Issues **#58-#121** (64 total) are the
subject of this plan. All 64 are **open** at the time of writing. The audit was
run against `d060481`.

The findings are grouped into **nine waves**. A wave is a shippable vertical
slice: one branch, one PR, all the fixes and their tests together. Within a wave
the issue numbers are ordered so a reviewer can read the diff top-to-bottom.

Severity follows `audit/README.md`: **Critical** silently corrupts the default
ingest path; **High** is a wrong number, wrong answer, or crash in a documented
workflow; **Medium** is narrower incorrect behavior, cross-request leakage,
event-loop stalls, or a real resource bug; **Low** is hardening, dead code,
misleading telemetry, duplication, or hygiene.

## Ground rules

- One branch per wave, prefixed `codex/` per AGENTS.md (for example
  `codex/wave-1-ingest-correctness`). One PR per wave, closing the issues it
  resolves by number.
- Commit messages: `<type>(<scope>): <imperative summary>`.
- Land each fix with its test in the same PR. The audit repeatedly shows defects
  shipped because the existing tests asserted the wrong thing (row counts instead
  of values, legacy parser instead of V2, no mixed units, no cache isolation).
- Backend wave gate: `make test-backend`, `make lint-backend`,
  `make typecheck-backend`. Frontend wave gate: `make test-frontend`,
  `make lint-frontend`, `make typecheck-frontend`. CI enforces 80% global,
  90% ingestion, and 70% LLM coverage.
- Never commit personal exports, generated DuckDB files, GPX/ECG data, `.env`,
  coverage output, or build output.
- Resolve paths explicitly; `uv --directory backend` changes the process
  working directory.

## Wave overview

| Wave | Theme | Issues | Count |
| --- | --- | --- | --- |
| 1 | Ingestion correctness, and the tests that must catch it | #58, #115, #116, #59, #117, #60, #118 | 7 |
| 2 | Ingestion robustness, staging safety, GPX read | #62, #61, #63, #88, #64, #65, #66 | 7 |
| 3 | Query numeric correctness and period labels | #119, #67, #68, #69, #70, #71, #72 | 7 |
| 4 | Chat cache correctness and app-state wiring | #74, #75, #120, #96, #73, #89, #80 | 7 |
| 5 | Async/event-loop correctness on chat and settings | #79, #81, #77, #78, #76, #121, #82 | 7 |
| 6 | Dashboard caches, diagnostics, imports, startup | #83, #111, #84, #113, #85, #86, #87, #112 | 8 |
| 7 | Local planner correctness and provider boundary | #90, #91, #92, #93, #94, #95 | 6 |
| 8 | Frontend correctness | #99, #100, #101, #102, #103, #104, #106 | 7 |
| 9 | Frontend polish and repository hygiene | #105, #107, #108, #109, #110, #97, #98, #114 | 8 |

Total: 64 issues.

---

## Wave 1 — Ingestion correctness, and the tests that must catch it

This is the critical path and should ship first and alone. ING-1 is the only
Critical finding: the default V2 ingest writes an empty `activity_type` for
every workout. It reached production because the suite counts rows instead of
checking values and seeds through the legacy parser. Fixing the value without
fixing the two test gaps leaves the same hole open for the next regression, so
the test work is part of this wave, not a follow-up.

1. **#58 ING-1** (Critical) — read `workoutActivityType` in `bytescan.py`
   (give the workout branch its own attribute pattern; Apple uses a capital
   `T`). Assert the stored value.
2. **#115 TST-1** (High) — replace row-count-only V2 assertions with value-level
   checks (`activity_type`, `duration`/`duration_unit`, route point counts,
   HRV beat counts); extend worker-invariance to the workout tables.
3. **#116 TST-2** (High) — parameterize the shared fixture helper to seed through
   `ingest_v2` so the contract, dashboard, chat, and cache suites exercise the
   default path; keep one explicit legacy-parser suite.
4. **#59 ING-2** (High) — replace the manual `sys.argv` loop in `run.py` with
   `argparse` so `export.xml --workers 2` no longer reports "File not found: 1".
5. **#117 TST-3** (Medium) — CLI test (subprocess or `capsys`) running
   `["export.xml", "--workers", "2"]` and asserting the parsed worker count.
6. **#60 ING-3** (High) — log the already-resolved worker count; stop calling
   `int()` on the raw `TTI_INGEST_WORKERS` value so `auto` no longer aborts
   a real import from a logging line.
7. **#118 TST-4** (Medium) — CLI-level tests with
   `TTI_INGEST_WORKERS=auto` and `not-a-number` asserting exit 0.

**Exit criteria.** `SELECT DISTINCT activity_type FROM workouts` returns real
types after a V2 ingest; the two documented CLI forms both exit 0; the new
value assertions fail if `bytescan` regresses.

---

## Wave 2 — Ingestion robustness, staging safety, GPX read

The remaining ingestion findings plus the two file-handling safety items
(#63 staging swap, #88 route read).

1. **#62 ING-5** (Medium) — make `_parse_int` tolerant like `_parse_float`
   (or share one numeric helper) so one malformed attribute cannot abort a whole
   import.
2. **#61 ING-4** (Medium) — parse the clock-format HRV beat time
   (`4:53:04.58 PM`) or accept both forms, count unparsed values in the report,
   and update the fixture to the real Apple format.
3. **#63 ING-6** (Medium) — take an advisory lock for the whole import, fsync the
   staging file and its directory before `os.replace`, and give the API a
   documented reconnect-after-import path.
4. **#88 API-15** (Low) — resolve `workout_routes.file_path` and require it to
   live under the export directory; parse with
   `resolve_entities=False, no_network=True`.
5. **#64 ING-7** (Low) — scope the `# ruff: noqa: S608`, bind or escape the
   shard directory, delete the no-op loop, and pass the table list explicitly
   instead of parsing SQL text.
6. **#65 ING-8** (Low) — split `CREATE TABLE IF NOT EXISTS` from an explicit
   destructive `reset_schema()`.
7. **#66 ING-9** (Low) — give each dry-run check a status (`pending`) or list
   only the checks the selected mode performs.

**Exit criteria.** A malformed numeric attribute degrades one row instead of
aborting the run; two concurrent imports serialize instead of losing work; a
non-GPX or out-of-root path is refused; the dry-run report does not advertise
checks it has not run.

---

## Wave 3 — Query numeric correctness and period labels

QRY-1 and QRY-2 are the wrong-total bugs a user sees on the dashboard and in
chat. Both are invisible to the current suite until a mixed-unit fixture exists,
so TST-5 leads the wave. QRY-3 is the same unit-handling surface.

1. **#119 TST-5** (Medium) — add a fixture with one `hr` workout, one `min`
   workout, one kJ and one kcal energy row in the same period. Prerequisite for
   the next two.
2. **#67 QRY-1** (High) — convert duration units inside the period-summary and
   comparison aggregates (`hr * 60`), or reuse `minutes_from_duration` per row;
   make the helper explicit about the units it accepts.
3. **#68 QRY-2** (Medium) — normalize energy to kJ
   (`kcal * 4.184`) and decide explicitly what an unknown unit does.
4. **#69 QRY-3** (Low) — extract one `distance_to_metres_sql` /
   Python helper to replace the six copy-pasted `CASE` expressions; make
   unknown units visible rather than silently metres.
5. **#70 QRY-4** (Low) — express "all time" with `None`-aware SQL or the
   dataset profile instead of the 1970/2100 sentinels.
6. **#71 QRY-5** (Low) — build period-summary titles from the same label
   vocabulary the comparison path uses ("June 2026"), or leave the title empty.
7. **#72 QRY-6** (Low) — remove the `.format()` interpolation from
   `_SQL_TOP_WORKOUTS` (static variants or an asserted whitelist).

**Exit criteria.** 1 hr + 60 min totals 120 min; mixed kJ/kcal sums convert; the
fixture assertions cover both, and the distance conversion exists once.

---

## Wave 4 — Chat cache correctness and app-state wiring

The two High cache bugs (#74 degraded answers, #75 disambiguation replayed
elsewhere) plus their missing tests (#120) are one theme: the response cache
stores things it should not. #96 is what makes the fallback text safe to cache
once #74 lands. #73 is the registry-validation gap. #89 and #80 both change
migration and `_ensure_ready()` semantics and must land together.

1. **#74 API-1** (High) — skip `put_cached_response` when the envelope's
   provenance is a fallback or carries an error; add a cacheable predicate.
2. **#75 API-2** (High) — treat disambiguation and conversation-scoped follow-ups
   as non-cacheable, or include conversation identity in the key.
3. **#120 TST-6** (Medium) — promote the fallback-cache and disambiguation repro
   scripts into an isolation integration test.
4. **#96 LLM-7** (Low) — drop the display rewriting from tool dispatch; coerce,
   strip, and bound the fallback text through a Pydantic model.
5. **#73 QRY-7** (Low) — type `metric_id` against `METRIC_CATALOG` and call
   `validate_query_catalogue()` once at startup.
6. **#89 API-16** (Medium) — inject the lifespan repositories via
   `Depends(...)` on every route; make the v2-v4 migrations `IF NOT EXISTS`,
   transactional, and guarded by a process-wide lock.
7. **#80 API-7** (Medium) — add `self._ensure_ready()` to
   `add_completed_turn`, `finish_turn`, and `terminate_turn`.

**Exit criteria.** A provider-down fallback is never replayed as cached success;
a disambiguation prompt is never served into another conversation; two
first-requests cannot collide on the state database.

---

## Wave 5 — Async/event-loop correctness on chat and settings

The blocking-work items form one class: cancel/error paths (#79), model
start/stop (#77), and the settings probe plus per-metric scans (#78). #81 is the
wasted duplicate profiling/planning on the chat miss path. #76 and #121 are one
behavior-plus-test pair.

1. **#79 API-6** (Medium) — push the cancel/error `terminate_turn` calls
   through `asyncio.to_thread`.
2. **#81 API-8** (Medium) — pass the profile and resolved plan from
   `_prepare_chat` into the orchestrator; build the remote prompt after the
   local-plan check.
3. **#77 API-4** (Medium) — `await asyncio.to_thread(litert_start)` and the
   same for stop.
4. **#78 API-5** (Medium) — offload the `GET /settings` payload, and replace
   the per-metric `COUNT(*)` scans with one `GROUP BY type`.
5. **#76 API-3** (Medium) — move the sleep source policy into one shared
   fragment or view used by both `/sleep` and `/sleep/stages`.
6. **#121 TST-7** (Low) — integration test with an `AutoSleep` row asserting
   the two sleep endpoints agree.
7. **#82 API-9** (Low) — treat a missing pending turn id as an error and check
   the `finish_turn` return value.

**Exit criteria.** The event-loop repro shows no multi-second stall in
`llm/start` or `GET /settings`; the sleep panels agree; no turn is left
silently pending.

---

## Wave 6 — Dashboard caches, diagnostics, imports, startup

Two observability items (#83, #111), the dashboard capability cache addressed
from both ends (#84 code, #113 boundary), the import manager (#85), health-db
deletion (#86), and the startup block (#87, #112).

1. **#83 API-10** (Low) — record `request.cache_mode` in both chat diagnostics
   paths instead of the fabricated literals.
2. **#111 INF-1** (Medium) — validate payload keys against the meta-key
   allowlist and reduce value redaction to secret-shaped patterns; test both
   directions (secrets scrubbed, benign identifiers intact).
3. **#84 API-11** (Low) — evict the least-recently-used entry
   (`move_to_end` or `functools.lru_cache`); make `CapabilitiesGlobal`
   `frozen=True` and copy on return.
4. **#113 INF-3** (Low) — settle the capability-cache boundary (return copies, or
   key by dataset version) so it cannot be mutated by a handler.
5. **#85 API-12** (Low) — add a subprocess timeout and cancel path, prune the
   job dict on insert, and surface the upload size cap in the UI.
6. **#86 API-13** (Low) — serialize `delete_health_database` against the
   connection pool and return a clear error when the file cannot be removed.
7. **#87 API-14** (Low) — make allowed origins configurable, decide the SPA mount
   per request, and derive the version from package metadata.
8. **#112 INF-2** (Low) — return a JSON 404 for unmatched `/api/*` before the
   SPA catch-all, and make an explicit decision about the docs endpoints.

**Exit criteria.** A benign `{'table': 'workout_routes'}` survives logging
while secrets are scrubbed; evicted entries are the LRU, not the oldest inserted;
an unmatched `/api/` path 404s as JSON; the version and origins are traceable
to configuration.

---

## Wave 7 — Local planner correctness and provider boundary

The deterministic planner is the privacy boundary, and #90-#92 are it being
wrong about the question: "last year", activity substrings, and week comparisons.
#93-#95 are the conversation loader, the gateway cache, and the LiteRT lifecycle.

1. **#90 LLM-1** (Medium) — match period words with word boundaries, add an
   explicit `last year` branch, and pick a granularity that keeps the bucket
   count bounded.
2. **#91 LLM-2** (Medium) — match whole words and require an activity phrase near
   a workout word; extract one shared vocabulary module for both planners.
3. **#92 LLM-3** (Medium) — branch `_comparison_plan` on week vs month
   granularity with date-range labels; add a test per granularity.
4. **#93 LLM-4** (Medium) — add a plan-only conversation loader that selects
   `id, question, canonical_plan_json, created_at` and filters to completed
   turns.
5. **#94 LLM-5** (Medium) — guard the gateway cache with a lock, close evicted
   clients, and give shutdown a quiet period or in-flight drain.
6. **#95 LLM-6** (Low) — return `None` for a missing LiteRT binary, verify
   process ownership before signalling, lock the start/stop pair, and reap a
   server whose pidfile write failed.

**Exit criteria.** The planner repro no longer mistypes "last year", "brunch",
"cyclone", or a week comparison; the gateway leaks no clients on a settings
change; a missing binary reports unavailable.

---

## Wave 8 — Frontend correctness

FE-1 is the one High frontend bug (concurrent submissions stranding turns and
landing answers on the wrong entry). The rest are the load/selection staleness
bugs and the error-message gap.

1. **#99 FE-1** (High) — track in-flight requests in a
   `Map<turnId, AbortController>`, settle turns by id with `map` instead of
   position `slice`, and abort outstanding requests on conversation switch.
2. **#100 FE-2** (Medium) — swap the inverted fallback heading and assert it.
3. **#101 FE-3** (Low) — branch `formatDateOnly` on date-only vs full instant.
4. **#102 FE-4** (Medium) — route `loadMoreWorkouts` through the scope
   generation guard, abort the pending page, and surface an inline error.
5. **#103 FE-5** (Medium) — pass an `AbortSignal` into `fetchWorkoutDetail`
   and guard the state writes.
6. **#104 FE-6** (Low) — require a non-empty title, show save errors, and
   reconstruct the mode from the query just written.
7. **#106 FE-8** (Low) — share one `checkedFetch` helper that reads the
   backend's `detail`.

**Exit criteria.** Two live submissions cannot strand a turn or land an answer on
the wrong entry; the detail panel never shows a stale workout; failures show the
backend's explanation.

---

## Wave 9 — Frontend polish and repository hygiene

Low-severity polish and the two remaining LLM-hygiene items.

1. **#105 FE-7** (Low) — extract one banner component and phrase it around the
   failing request instead of a hardcoded port.
2. **#107 FE-9** (Low) — return a cleanup that aborts and clears the timer, and
   retry with bounded backoff.
3. **#108 FE-10** (Low) — default/validate envelope fields in the dispatch and
   stop overloading `text` for the unknown-template message.
4. **#109 FE-11** (Low) — keep the `workouts` tab spelling when the view is
   workouts, and reject control characters in the query parser.
5. **#110 FE-12** (Low) — debounce the conversation search, replace
   `window.prompt`, fix the sidebar count label, remove the dead provider
   branch, and fix the falsy cache check.
6. **#97 LLM-8** (Low) — record one benchmark event per `best_of` invocation
   and fail when the best run still exceeds the threshold.
7. **#98 LLM-9** (Low) — parse inline comments in the env loader, make
   `get_model()` use the same path (or delete it).
8. **#114 INF-4** (Low) — resolve or drop the `R1-*` / `GH-*` comment IDs, or
   add `docs/WORK_ITEMS.md` mapping each namespace to its tracker.

**Exit criteria.** No stale connection banner, no unchecked envelope casts, no
comment referencing a tracker a reader cannot resolve.

---

## Cross-cutting dependencies

- **Test-side work is not a follow-up.** #115, #116, #117, #118, #119, #120, and
  #121 are placed in the same wave as the defect they guard, because the audit
  shows each defect shipped through a test that asserted the wrong property.
- **#89 and #80 land together.** Both change migration and `_ensure_ready()`
  semantics in `app_state.py`; splitting them risks a half-guarded store.
- **#96 depends on #74.** Bounding and validating fallback text is only durable
  once fallbacks stop being written to the cache.
- **#84 and #113 are the same cache.** They must land in one PR or the frozen
  payload and the copy-on-return will disagree.
- **#87 and #112 are the same startup block** in `main.py`. #73's startup call
  to `validate_query_catalogue()` also touches that block; if #73 ships in an
  earlier wave, keep the edit isolated so the later startup work is a clean
  merge.
- **Wave 1 is release-blocking on its own.** If the schedule slips, shipping
  Wave 1 alone restores data correctness for every V2 import; Waves 2-9 are
  improvements on a correct base.

## Full issue index

| Issue | ID | Severity | Wave | Title |
| --- | --- | --- | --- | --- |
| #58 | ING-1 | Critical | 1 | V2 ingestion stores an empty `activity_type` for every workout |
| #59 | ING-2 | High | 1 | `--workers N` after the file path aborts with "File not found: 1" |
| #60 | ING-3 | High | 1 | a non-numeric `TTI_INGEST_WORKERS` kills the import from a logging line |
| #61 | ING-4 | Medium | 2 | HRV beat rows are "bug-compatible", so the table stays empty on real exports |
| #62 | ING-5 | Medium | 2 | `_parse_int` raises where `_parse_float` returns `None` |
| #63 | ING-6 | Medium | 2 | staging file and `os.replace` have no lock, no fsync, and no reconnect story |
| #64 | ING-7 | Low | 2 | reconciliation builds SQL as strings and keeps a no-op loop |
| #65 | ING-8 | Low | 2 | `SQL_CREATE_TABLES` drops every table unconditionally |
| #66 | ING-9 | Low | 2 | the dry-run report advertises checks that have not run |
| #67 | QRY-1 | High | 3 | duration totals sum mixed units without converting |
| #68 | QRY-2 | Medium | 3 | active energy is summed across rows whose units are never checked |
| #69 | QRY-3 | Low | 3 | the distance conversion is duplicated six times and silently treats unknown units as metres |
| #70 | QRY-4 | Low | 3 | "all time" is expressed with hardcoded 1970 and 2100 sentinels |
| #71 | QRY-5 | Low | 3 | period-summary titles use ISO dates while every other label is human |
| #72 | QRY-6 | Low | 3 | one query is assembled with `.format()` in a module that documents avoiding it |
| #73 | QRY-7 | Low | 4 | an unknown metric id produces an empty chart instead of a rejection |
| #74 | API-1 | High | 4 | degraded answers are cached and replayed as successful ones |
| #75 | API-2 | High | 4 | a disambiguation prompt is cached and replayed into other conversations |
| #76 | API-3 | Medium | 5 | the two sleep panels use different source filters |
| #77 | API-4 | Medium | 5 | starting or stopping the local model stalls the whole API |
| #78 | API-5 | Medium | 5 | `GET /settings` does a synchronous HTTP probe and per-metric COUNT scans on the loop |
| #79 | API-6 | Medium | 5 | cancel and error paths run SQLite writes on the event loop |
| #80 | API-7 | Medium | 4 | three repository writers skip the migration guard |
| #81 | API-8 | Medium | 5 | every cache-miss turn computes the data profile twice and plans twice |
| #82 | API-9 | Low | 5 | a missing pending turn id is sent as an empty string and ignored |
| #83 | API-10 | Low | 6 | chat diagnostics record fabricated cache modes |
| #84 | API-11 | Low | 6 | the dashboard capability cache evicts the wrong entry and hands out a mutable object |
| #85 | API-12 | Low | 6 | the import manager has a fixed size cap, no subprocess timeout, and no persistence |
| #86 | API-13 | Low | 6 | the health database can be unlinked while connections are open |
| #87 | API-14 | Low | 6 | startup hardcodes the dev origin, decides the SPA mount at import time, and reports a stale version |
| #88 | API-15 | Low | 2 | a route path taken from the database is parsed without validation |
| #89 | API-16 | Medium | 4 | per-request repositories re-run the migration chain, so two first requests can collide on the state database |
| #90 | LLM-1 | Medium | 7 | "last year" resolves to the current year-to-date; any sentence containing "year" matches |
| #91 | LLM-2 | Medium | 7 | Activity detection is unanchored substring matching, so non-workout questions get workout answers |
| #92 | LLM-3 | Medium | 7 | The comparison planner accepts the word "week" but always compares calendar months |
| #93 | LLM-4 | Medium | 7 | Every cache miss re-reads and re-parses the whole conversation to build follow-up contexts |
| #94 | LLM-5 | Medium | 7 | The gateway cache and circuit-breaker state are shared mutable state with no lock or drain |
| #95 | LLM-6 | Low | 7 | LiteRT lifecycle: a binary that does not exist reports as available, and `stop()` kills a pid it does not own |
| #96 | LLM-7 | Low | 4 | Display formatting is done by unanchored `str.replace` inside tool dispatch, and the fallback tool forwards unvalidated model text |
| #97 | LLM-8 | Low | 9 | The benchmark harness records every run as if it were the result and never fails on its own threshold |
| #98 | LLM-9 | Low | 9 | The env-file loader mutates the process environment and drops inline comments; `get_model()` bypasses it |
| #99 | FE-1 | High | 8 | concurrent submissions strand a turn in "loading" and can land an answer on the wrong entry |
| #100 | FE-2 | Medium | 8 | the fallback heading is inverted: content-bearing fallbacks say "Answer unavailable" |
| #101 | FE-3 | Low | 8 | `formatDateOnly` silently shifts offset-bearing timestamps by a day |
| #102 | FE-4 | Medium | 8 | `loadMoreWorkouts` appends into whatever scope happens to be loaded |
| #103 | FE-5 | Medium | 8 | workout detail can render a stale workout after the selection changes |
| #104 | FE-6 | Low | 8 | applying and saving dashboard views drops state and errors |
| #105 | FE-7 | Low | 9 | the "make dev on port 8000" banner is wrong whenever Vite serves the app |
| #106 | FE-8 | Low | 8 | most API clients discard the backend's problem `detail` |
| #107 | FE-9 | Low | 9 | the backend health probe can fire after unmount and never retries |
| #108 | FE-10 | Low | 9 | template dispatch trusts the envelope with unchecked casts |
| #109 | FE-11 | Low | 9 | `tab=workouts` deep links rewrite themselves on first click |
| #110 | FE-12 | Low | 9 | smaller issues kept together |
| #111 | INF-1 | Medium | 6 | the log redactor checks values, not keys, so it destroys benign identifiers and misses the leak it was written for |
| #112 | INF-2 | Low | 6 | startup and HTTP surface hardening |
| #113 | INF-3 | Low | 6 | the dashboard capability cache is a mutable process global |
| #114 | INF-4 | Low | 9 | no in-code defect markers, and 21 comments point at work items a reader cannot resolve |
| #115 | TST-1 | High | 1 | ingestion tests assert row counts, never values, so ING-1 hides behind a green suite |
| #116 | TST-2 | High | 1 | most integration tests seed through the legacy parser, so the default ingest path is never the one under test |
| #117 | TST-3 | Medium | 1 | nothing invokes the ingest CLI |
| #118 | TST-4 | Medium | 1 | the CLI environment variable path is untested for non-numeric values |
| #119 | TST-5 | Medium | 3 | the fixture has no mixed-unit data, so the unit-summing defects cannot fail a test |
| #120 | TST-6 | Medium | 4 | no test covers cache poisoning or cross-conversation cache isolation |
| #121 | TST-7 | Low | 5 | nothing asserts the two sleep panels agree |
