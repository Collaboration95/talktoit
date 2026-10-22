# Synthetic performance preparation — #179

Status: **harness prepared; representative measurements and every candidate decision pending**.
Preparation starts at `475e67347a1fce1c8fe7be96143782f276923c38` (supported #140 baseline and
maintenance #204). The preparation branch also includes the supplied
#203/#206 integrations through `c4613413594dd84b4ab9d79dee08487d2c1e8522`.
The denied-provider HTTP probe asserts the additive `fallback.reason=provider_unavailable`
contract while keeping answer contents out of the report. Follow-up merges latest dev
through #205 (`d2d33b9`, PR head `bbc269a`) and uses its public effective-path/connection APIs.
The acceptance evidence index is preserved from that merge. Final compatibility consumes
#207's committed `bae7984c69041019cb851c595e2bbb0d33233552` and integrated dev `b9ccec6`.
Core lifecycle and ENGINEERING changes are consumed only by merge. Harness verification and
query connections now use the public leased `dataset_snapshot()` API, with identity from
the same immutable snapshot. Analytics writers retain ownership of their production paths.
Sibling agents are using the machine. Functional test durations are not baseline evidence.
No throughput, benefit, calibrated budget, go or no-go is claimed in this preparation batch.
Parent owns quiet measurement, integrated browser acceptance, final review and batching.

## Pilot first, after the parent declares the machine quiet

Use Python 3.12+ and the committed backend/frontend locks. On the reference Mac:

```sh
export PATH=/opt/homebrew/opt/node@20/bin:$PATH
export PYTEST_XDIST_AUTO_NUM_WORKERS=2
uv sync --directory backend --dev --locked --python 3.12
npm --prefix frontend ci
make bench
/usr/bin/time -p make bench-synthetic BENCH_ARGS="--cases representative --seeds 137 --workers 1 --ingestion-warmups 0 --ingestion-samples 1" > /tmp/tti-synthetic-pilot.json
```

This pilot performs **one** full representative import, then 2 discarded and 20 retained
query/HTTP workload processes against its one verified generation. It establishes plumbing
and an initial execution-cost estimate, not a performance baseline or SLA. The outer `time`
includes build, corpus generation, harness parity checks and cleanup. The separate
`workload_process_wall` metric includes app startup/recovery validation, state projection,
request/query/EXPLAIN work and shutdown; do not budget the matrix using HTTP timings alone.
Inspect this pilot before authorizing a whole quiet matrix. No pilot is run during this
concurrent-agent preparation phase.

When the pilot's cost is acceptable, run the matrix sequentially:

```sh
make bench-synthetic BENCH_ARGS="--workers 1 2 4" > /tmp/tti-synthetic-baseline-a.json
make bench-synthetic BENCH_ARGS="--workers 1 2 4" > /tmp/tti-synthetic-baseline-b.json
```

Both matrices use both sizes, seeds 137/271, and independent sampling groups:

- **Ingestion:** `--ingestion-warmups 1 --ingestion-samples 3`. Median and nearest-rank p95
  use only 3 retained full CLI imports, so **p95 is the maximum**, with no tail-latency or
  SLA claim. This applies to import wall, rows/s and aggregate peak RSS.
- **Workload:** `--warmups 2 --samples 20`. All cheap query/HTTP metrics and workload process
  wall use 20 retained processes against one committed generation per case/seed/worker.
  Every cold app gets fresh state/cache. Nearest-rank p95 is the nineteenth ordered sample.
  CLI `--samples` below 20 is rejected; tiny functional tests call the Python API directly
  with fewer trials and make no performance claims.

The explicit three-worker matrix has 12 configurations: **48 imports and 264 workload
processes per run**, including discarded warmups. Two runs have 96 imports, not 20 imports
per configuration merely to sample HTTP. Default workers are 1/2 (8 configurations).
These are arithmetic invocation counts, not measured budgets. Increase import samples
(e.g. `--ingestion-samples 5`) only if the pilot/repeated comparisons show inconclusive
noise; record why the extra cost is needed. Never automatically escalate full imports to
20 or apply the workload count to ingestion. Compare like group/counts across variants.

Schema v2 reports `ingestion_sampling`, `workload_sampling`, a group and actual retained
sample count on every metric. A model validator rejects mixed counts/groups and duplicates.
Warmups never contribute to summaries or retained RSS snapshot counts. Compare runtime,
revision, locks, seed, source SHA-256/bytes/counts, workers and sampling metadata before
comparing results. Do not select the fastest trial. Do not run under coverage, xdist,
concurrent builds/tests or other imports. Use AC power and disclose power mode and competing
workloads. CPU/RAM, OS, Python, Node/npm, DuckDB, commit/locks and dirty status are recorded.

A bounded check of plumbing, when needed after changes, is:

```sh
uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py --no-cov -n 2 -q
```

Those functional tests intentionally use only 24 records, six workouts and three days.
They assert no latency budgets and publish no timings. Existing `make bench`/`best_of`
policies remain unchanged; the new runner never calls `best_of`.

## Corpus, sampling and correctness

Recipe v1 streams XML without a full XML string in memory. Small: 2,048 records, 64
workouts, 28 days. Representative: 500,000 records, 8,192 workouts, 180 days. These are
explicit stress sizes, not a claim about a person's export or population distribution.
Both seeds have the same counts and different content hashes. Each corpus cycles through
steps, resting HR, HRV and categorical sleep, includes real numeric zeros, reversed
attribute order, self-closing/nested records, record metadata, two workout types/sources,
events, elevation metadata, and three statistics per workout with distance/energy unit
conversion. It contains no GPS routes or beat children; their expected counts are zero.
Dates are fixed synthetic dates, independent of the computer clock.

Each ingestion warmup/sample starts a new official
`python -m app.ingest.run ... --workers N --report-json` subprocess with owned configured
DB, state and shard paths. Legacy fallback is disabled. The outer wall timer spans process
launch through exit: syntax validation, byte scanning, reconciliation, final compatibility
gate, durable immutable generation validation/publication, manifest projection and shutdown.
It does not trust the coordinator's earlier `total` field. Extra harness parity verification,
XML generation and frontend build are outside this timer. Rows/s uses all nine table row
counts divided by full wall duration, not just top-level XML records/s.

Every import trial, including warmups, verifies V2 mode/worker count, all nine exact counts,
active/report generation identity, six child-parent anti-joins, known step sum and workout
duration sum. Verification holds public `dataset_snapshot()` under the isolated
configuration and reads identity, root and connection from that leased tuple; it never opens
a configured legacy file directly or borrows identity from a SQLite projection. All but the
final verified import directory are cleaned before cheap sampling. The final generation is
shared read-only by every workload process; it is never re-imported to collect HTTP samples.

Each workload gets a new app-state path, and real app startup recovers/projects that same
committed generation through the existing lifecycle APIs. No pointer/manifest formats,
projection protocol, directory naming or generation files are cloned/reimplemented here.
Every workload checks the expected generation id from its leased snapshot and rejects
pre-existing app state. No-active/tombstoned snapshots fail the benchmark before query/HTTP
sampling, rather than contributing empty results. Startup ownership recovery and deletion
handling remain enabled through the production lifecycle; they are never stubbed away. Cold
and fresh requests must profile once and remain local; exact cache hits must profile zero
times. The tiny regression deliberately creates an incorrect configured legacy DB after
import to prove both parity verification and queries follow the managed generation.
It also checks independent invocation counts, injected summary/memory oracles, and exact
sample-group validation. Other fixture tests verify corpus parity at workers 1/2/4 and
reject broken child counts. Import/fallback/identity/parity/network/isolation failures,
nonfinite observations or unobserved memory reject the run rather than publishing success.

## Memory and cost boundaries

The monitor samples `/bin/ps -axo pid=,ppid=,rss=` for the importer parent and recursively
its descendants on both macOS and Ubuntu. RSS is KiB on these platforms and is multiplied
by 1,024. Report the maximum **simultaneous sum** per trial, then median/p95 of those peaks;
never sum individual process peaks. The monitor itself and the outer benchmark process
are excluded. Sampling runs on a separate thread every 50 ms plus snapshot collection
time; report the interval and number of nonzero snapshots. Wall time is captured on child
exit before sampler finalization. RSS double-counts shared pages and can miss short-lived
process peaks; it is a sampled lower bound on peak summed RSS, not PSS, USS or a heap
allocation measurement. The monitor adds overhead consistently to baseline and variants.
No platform-dependent `ru_maxrss` interpretation or unobserved child memory is substituted.

After the ingestion group, each workload trial starts a new process. It boots the real
app lifespan, calls real ASGI routes and denies socket connect/DNS, model startup/health/stop and inference via
injected gateway stubs. Child environment inherits only tool discovery/locale, discarding
user credentials, provider config and app paths. Unsupported chat returns a denied-provider
fallback. Deterministic/cached chat must never invoke the stub provider. Provider latency
is **unmeasured: no inference**, not a fabricated zero-duration model call.

Chat costs separately identify the first request in a fresh app/state/cache, a forced
`fresh` request for that now-cached question, a distinct fresh deterministic question,
an exact cache hit, and denied-provider fallback. Profile call count is instrumented and
checked per request (one scan for uncached/fresh, zero for exact). Cold/warm local latest/ranked/paged/trend queries are timed
separately using new vs repeated DuckDB connections. HTTP runs before those local scans;
OS filesystem caches are not flushed or controlled. HTTP metrics include middleware,
validation, serialization, route state and query work but use in-process ASGI: they exclude
TCP/TLS/browser/transfer costs. Do not subtract unrelated query timings to invent pure
HTTP overhead or equate connection-cold with a cold disk.

Parent's separate functional browser receipt at `d2d33b9` observed nine initial resources
(status plus eight dashboard requests), then eight dashboard requests on week-to-month
toggle. The actual viewport was 390×844 with document width 390. The local visual-check
JSON/script/screenshots record this without timing claims. Native T3 resize reported width
1402 and two snapshot timeouts; the parent's installed Playwright fallback provided that
functional evidence. It is not a timed baseline or acceptance of this final harness/base;
parent reruns integrated browser behavior after analytics. This harness adds no browser
execution and keeps its explicit per-report browser-evidence limitation.

The scripted dashboard mount requests nine resources concurrently (summary, workouts,
volume, steps, heart, sleep, stages, capabilities, status), followed by a warm repetition.
Counts describe **one scripted mount**, not observed browser effect behavior. Current
integrated week/month counts and scope/cancellation behavior still require the parent's
post-analytics browser/component acceptance. `browser_evidence=unavailable_requires_browser_run` is an explicit harness
limitation; parent supplies integrated browser acceptance. Initial production JS/gzip
bytes are the unique entry/static-import closure in the freshly built Vite manifest;
dynamic imports are excluded. Gzip is computed independently per file with mtime zero.
Bytes alone establish neither cold-load latency nor chart first-use performance.

## Publication and experiment protocol

Only a closed Pydantic report is printed to stdout. Root build output goes to stderr so
stdout can be redirected to JSON. It contains corpus counts/hashes, machine/runtime,
fixed metric identifiers, numeric summaries, explicit limitations and no health rows or
values, question text, SQL, plans, paths, hostnames, credentials or child logs. Unknown
fields/identifiers are rejected. Generated XML/DB/state/shards live in disposable temporary
storage; never commit them, frontend dist or coverage. Failures produce only a fixed status.

Latest/ranked/cursor-paged joins are exercised by production query helpers. The bounded
plan matrix now runs **14 fixed variants** once inside each existing query workload's
leased EXPLAIN context, after the original cold/warm query metrics. It reuses the already
parity-verified generation; no variants create another XML corpus or official import.

- `latest_broad` / `latest_selective`: no activity/date filter versus the actual anchor
  activity and its Singapore-local day, using `get_last_workout`.
- `ranked_broad` / `ranked_selective`: all dates versus that day, using `get_top_workouts`
  with distance ranking. The public ranked helper requires an activity type, so broad
  here means broad dates for that activity; there is no invented all-type ranking API.
- `paged_broad_first` / `paged_broad_next`, plus corresponding `date`, `type`, `source`
  and `selective` first/next pairs: independent date-only/type-only/source-only predicates,
  then combined predicates, using `get_workout_collection`. Broad paging spans the fixed
  synthetic range 2000–2100. First pages contain one row; every next cursor is the actual
  `(start_date, id)` of the returned first-page row. A legitimate empty next page is still
  executed and analyzed, and its reported result count is zero.

The initial broad page is itself one matrix case and supplies the real anchor's date,
activity and source, keeping all selective first pages nonempty on the generated/fixture
corpora. Latest/ranked helpers have no source-filter argument; source-only and combined
source filtering are exercised through pagination, rather than changing production SQL
or pretending unsupported helper parameters exist.

Each helper's actual parameterized statement is captured and passed unchanged to real
`EXPLAIN ANALYZE`, with the same bound arguments. No source-string assumption about DuckDB
executing complete aggregate subqueries is used. Private `workout_plan_variants(conn)`
results retain the real helper results and plan text for synthetic scratch inspection;
`explain_workout_joins(conn)` preserves the older three-plan private inspector. Neither raw
SQL, parameters, result rows nor plans are serialized into a published report.

The additive closed `plan_variants` report maps only fixed IDs to `success`, `result_rows`
and `operator_cardinality: null`. Result counts describe helper output rows (including
ranked helper null-primary filtering), **not operator scans or estimated cardinalities**.
Operator statistics are deliberately not collected; no version-specific JSON profiler is
used and no unsupported-capability claim is made. The installed DuckDB's text ANALYZE
support is exercised directly by the real-plan fixture tests. Scan/aggregate cardinalities
must be inspected privately or collected in a separately verified profiling experiment
before making any optimizer or summary-table decision. The original three family success
flags remain, together with all existing query timing, profile, provider and isolation
fields. Variant evidence must agree across warmup and retained workloads for the immutable
generation; missing/unknown variant IDs and arbitrary fields are rejected before publication.

The selective/subsequent-page **functional coverage gap is closed**. Actual representative
plan investigation, timings, filtered-aggregate/summary-table comparisons and candidate
selection remain pending the quiet measurement phase. Any later variant must preserve
result/order/null/unit parity and include summary-build cost/storage in full import costs.
This preparation authorizes no production query or schema change.

All candidate rows below are **pending measurement**, including no-change dispositions.
Use identical seeds/counts/workers/toolchain and interleaved baseline/variant runs with
independent warmups/counts: >=20 cheap workload trials and initially 3 full imports.
Repeat independently; escalate full import counts only for demonstrated inconclusive noise.
State an acceptable regression/noise margin before examining variant results, grounded in baseline variability.
Go requires repeatable benefit beyond that variability plus all parity/privacy gates;
no-go requires measurements showing the budget already holds or no useful gain, with a
concrete future trigger. Inconclusive evidence stays pending; source inspection cannot
establish a no-go. Proposed roadmap p95/worker/memory budgets remain uncalibrated.

| Contract | Bounded follow-up experiment and required oracle |
| --- | --- |
| #180 XML retention | Separate synthetic validation subprocesses, baseline vs safe sibling-shell cleanup; compare tree RSS and full import wall cost; nested, malformed, truncated and wrong-root accept/reject parity plus official counts/relations. Never skip validation. |
| #181 worker copies | Same boundary-heavy corpus at 1/2/4 workers; scratch bounded mmap matching vs copied ranges; compare process-tree RSS/full throughput; exact IDs/values/children and nonzero-range boundary ownership. |
| #183 write scopes | Hold preparation at a deterministic barrier while an unrelated app-state writer runs; measure writer median/p95 before release; terminal-once pending/cancel/failure/cache/history oracles. Coordinate generation owner before production edits. |
| #184 profile reuse | Distinct uncached questions and exact hits with profile-call counts; profile identity/import/delete/CLI override, immutable concurrent reuse and bounded eviction; compare chat median/p95 only after #161 identity integration. |
| #186 panel requests | Production browser with synthetic import: capture initial mount, week/month toggle, scope change and rapid toggle/scope; compare observed request counts and volume completion while stale responses/cancellation/errors remain correct. |
| #187 initial charts | Fresh manifest closure/gzip plus browser cold chat, first chart, cached navigation; exact loading/empty/error/fallback, original question and chunk-failure recovery. Bundle byte reduction alone is insufficient. |
| #188 SQL buckets | Scratch parameterized numeric SQL vs current get_trend; day/week/month, offsets/DST, sparse/null/zero/empty windows, SUM/AVG and unit equality; transferred row count, memory and median/p95. Do not alter sleep interval semantics. |

## Original preparation verification receipt (historical, schema v1)

The receipt below records `ac44f47` before durable activation. Current schema/defaults and
commands above supersede the old coupled sampling design; these historical passes do not
verify the follow-up or the current development branch.

Tests were written before the new harness modules; initial focused collection exited 2
with missing-module errors. Final functional/quality results are recorded with the
preparation handoff. Representative runs, tiny timing policies, candidate prototypes,
benefits/budgets, browser evidence and measured go/no-go dispositions are deliberately
pending the parent's quiet-machine follow-up. No PR or issue closure is made for this
single-issue preparation commit.

Final preparation gates on the #206 base (`c461341`), CPython 3.12.11, Node 20.20.2 /
npm 10.8.2, with disposable health/state paths and two pytest workers:

| Command | Exit | Evidence |
| --- | ---: | --- |
| `uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py --no-cov -n 2 -q` | 0 | 16 functional regressions; warmup exclusion, 1/2/4-worker parity, ASGI denial/fallback reason and privacy |
| `env -u TTI_LOCAL_AUTOSTART make test-backend` with `PYTEST_XDIST_AUTO_NUM_WORKERS=2` | 0 | 528 passed, global coverage 86.52% |
| `uv run --directory backend coverage report '--include=app/ingest/*' --fail-under=90` | 0 | 924/1,015 statements, 91.03% |
| `uv run --directory backend coverage report '--include=app/llm/*' --fail-under=70` | 0 | 1,270/1,532 statements, 82.90% |
| `make check` with supported Node 20 on PATH | 0 | Backend/frontend lint, format, types and version consistency |
| `npm --prefix frontend run build -- --manifest` with Node 20 | 0 | Production build plus manifest; existing large-chunk warning retained |
| Runtime metadata and real production-manifest parser assertions | 0 | Supported runtime validated; initial closure contains JS; no load-time claim |
| `make --dry-run bench-synthetic BENCH_ARGS='--samples 20 --warmups 2 --workers 1 2 4'` | 0 | New root command plumbing; actual timed matrix not executed |

The broad gates were repeated once after #206 changed backend planning/fallback contracts;
no representative measurement or tiny latency-policy run was attempted. Ubuntu execution
of the new process-tree sampler, representative runs twice, deeper selective/subsequent-page
plans, candidate prototypes/dispositions, browser load/toggle evidence, calibrated budgets,
and the parent's final integrated review remain outstanding. Existing macOS/Ubuntu CI
success from the maintenance batch is not execution evidence for this new harness.

## Follow-up preparation receipt (schema v2, durable generations)

Merged `origin/codex/dev-roadmap-20261022` through `d2d33b9` (#205, head `bbc269a`)
into the harness branch. The acceptance evidence index matches that base exactly; no
core lifecycle, connection, ingestion, HTTP, frontend or ENGINEERING edits were made
for this follow-up beyond merging existing content.

New regressions preceded implementation: the first focused run exited 1 with 3 failures
and 15 passes (missing independent options, no stale-state rejection, coupled signature).
An additional budget-metric regression also failed before that metric was added. Final
focused invocation of both harness test files with `--no-cov -n 2 -q` exited 0: **18 passed**.
They run tiny generated data only; injected timings/RSS values are statistical oracles,
not observations to publish as a baseline.

The integration oracle observes exactly 3 imports (1 discarded/2 retained) independently
of 4 workload subprocesses (1 discarded/3 retained). All workloads receive different fresh
state paths and the final import's one generation id. A deliberately wrong legacy DB is
ignored by managed-path verification and query lookup. Retained import wall/RSS and
workload summaries have their own expected medians/p95/counts; the warmup RSS snapshot
count is excluded. Wrong sample metadata is rejected. HTTP checks cover cold/fresh/exact
behavior, zero real provider/network use and the additive denied-provider fallback reason.
CLI defaults and the minimum 20 cheap samples are tested separately from the reduced-count
functional Python-API fixture.

`make check` with supported Node 20, Ruff lint/format and Pyright all exited 0. The pilot
root command was inspected with `make --dry-run` (exit 0); it was **not executed**. No quiet
pilot/matrix, candidate disposition, browser acceptance, new Ubuntu sampler execution,
PR, CI polling, issue closure or production optimization was performed. Parent owns the
next generation/cleanup integration, quiet pilot and measured candidate batch.

Final broader commands on the merged #205 base, with CPython 3.12.11, Node 20.20.2,
`PYTEST_XDIST_AUTO_NUM_WORKERS=2`, disposable DB/state paths and autostart unset for the
explicitly mocked lifecycle tests:

| Command | Exit | Evidence |
| --- | ---: | --- |
| `env -u TTI_LOCAL_AUTOSTART make test-backend` | 0 | 635 passed; global coverage 86.86% |
| `uv run --directory backend coverage report '--include=app/ingest/*' --fail-under=90` | 0 | 924/1,015 statements, 91.03% |
| `uv run --directory backend coverage report '--include=app/llm/*' --fail-under=70` | 0 | 1,270/1,532 statements, 82.90% |
| `make check` with Node 20 on PATH | 0 | Backend/frontend lint, format, type and version gates |

No coverage/test/CI threshold or production code was changed. Backend gates were run once
after the focused regressions passed; functional suite wall times under sibling load are
not baseline evidence. The retained unresolved measurement/browser/EXPLAIN limitations in
the original receipt remain, plus rerunning the pilot after #160–163 integration.

## Final leased-lifecycle compatibility receipt

Consumed committed #207 head `bae7984c69041019cb851c595e2bbb0d33233552`, then fetched and
merged its integrated dev merge `b9ccec6`. The acceptance evidence index is unchanged from
that origin dev state. No core, analytics, Makefile or ENGINEERING edits were made in this
compatibility change; existing content was consumed by merge only.

The original 18 harness tests passed on the merged lifecycle before implementation. New
regression assertions then failed first (exit 1, 2 failures/17 passes): import verification
had no bound snapshot and local queries acquired no generation leases. Verification now
reads the manifest/connection from the same public `dataset_snapshot()` context; the four
local query connections and EXPLAIN context also hold actual generation leases. No-active
snapshots reject sampling before empty/deleted data could become a benchmark observation.

The additional end-to-end tiny synthetic regression creates an active and retained
predecessor generation through the official CLI. Across two fresh app-state lifespans,
real ownership recovery stays enabled; JSON contents, stable lock inodes and both protected
generation references remain unchanged. It checks `chat-cache-v5`, exact/fresh/cold behavior,
no real providers/network and `fallback.reason=provider_unavailable`. It then deletes via
the public API and verifies empty snapshot identity and fail-closed query/HTTP sampling,
including a new startup after deletion. These are functional oracles, not timing evidence.

| Command | Exit | Evidence |
| --- | ---: | --- |
| `uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py --no-cov -n 2 -q` | 0 | 19 passed; original 18 plus leased-startup/retention/ownership/deletion regression |
| `uv run --directory backend pytest tests/unit/test_chat_cache.py tests/unit/test_cli_chat.py --no-cov -n 2 -q` | 0 | 23 passed; final cache-v5 and CLI contracts |
| `make check` with Node 20.20.2 on PATH | 0 | Lint, formatting, backend/frontend types and version consistency |
| `make --dry-run bench-synthetic` with the pilot and full arguments above | 0 | Both command paths inspected; neither measurement command executed |

Sampling remains independently 3 retained imports + 1 warmup and 20 retained workloads +
2 warmups. No sample/coverage/CI gate was weakened. The full backend/coverage receipts above
remain historical; this fast compatibility pass ran the focused commands listed here.
Parent owns the post-analytics browser acceptance, independent integrated review, quiet
pilot, matrix budget decision and measured candidate batch. No representative export,
pilot, baseline, benefit claim, new browser run, issue closure, PR or CI watcher was added.

## Selective and subsequent-page plan completion receipt

The two new regression tests were written before implementation and first exited 1 with
missing matrix/evidence types. The real-plan test imports the committed tiny synthetic
fixture once through the official V2 entry point and checks its nine-table parity. It
observes 2 latest, 2 ranked and 10 pagination calls to actual production helpers, then
verifies real ANALYZE plans for all 14 cases. It checks the real next-page cursor, IDs
3 then 2 in descending date order, a missing strength-workout distance remaining null,
independent filter arguments and genuinely empty filtered subsequent pages. Privacy tests
reject raw SQL/parameters/plans/rows/paths/question fields and invented operator numbers.
The existing end-to-end sampling test still asserts exactly 3 import calls and 4 workload
calls for its reduced-count fixture, proving plan variants do not multiply imports.

| Command | Exit | Evidence |
| --- | ---: | --- |
| `uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py tests/bench/test_workout_plan_variants.py --no-cov -n 2 -q` | 0 | 21 passed; complete variant matrix, closed publication, stable query/profile/provider/isolation and import-count contracts |
| `uv run --directory backend ruff check app/bench tests/bench/test_workout_plan_variants.py tests/bench/test_synthetic_integration.py` | 0 | Focused lint |
| `uv run --directory backend pyright` | 0 | Backend type check |
| `make check` with Node 20.20.2 on PATH | 0 | Repository static quality and version gates |

No production queries/schema, ENGINEERING, root command, sampling defaults or coverage
thresholds changed. The 600+ backend suite was not rerun for this bounded harness-only
addition. No representative pilot, baseline, live provider/network, timing/benefit/no-go
claim, PR, CI polling, subagent or wait for another writer was involved. The functional
selective/subsequent-plan limitation in older receipts is now superseded by this section;
quiet representative analysis and measured candidate dispositions remain with the parent.
