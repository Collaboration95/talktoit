# Synthetic performance preparation — #179

Status: **harness prepared; representative measurements and every candidate decision pending**.
Preparation starts at `475e67347a1fce1c8fe7be96143782f276923c38` (supported #140 baseline and
maintenance #204). The preparation branch also includes the supplied
#203/#206 integrations through `c4613413594dd84b4ab9d79dee08487d2c1e8522`.
The denied-provider HTTP probe asserts the additive `fallback.reason=provider_unavailable`
contract while keeping answer contents out of the report.
Sibling agents are using the machine. Functional test durations are not baseline evidence.
No throughput, benefit, calibrated budget, go or no-go is claimed in this preparation batch.
Parent owns quiet measurement, integrated browser acceptance, final review and batching.

## Reproduce after the parent declares the machine quiet

Use Python 3.12+ and the committed backend/frontend locks. On the reference Mac:

```sh
export PATH=/opt/homebrew/opt/node@20/bin:$PATH
export PYTEST_XDIST_AUTO_NUM_WORKERS=2
uv sync --directory backend --dev --locked --python 3.12
npm --prefix frontend ci
make bench
make bench-synthetic BENCH_ARGS="--warmups 2 --samples 20 --workers 1 2 4" > /tmp/tti-synthetic-baseline-a.json
make bench-synthetic BENCH_ARGS="--warmups 2 --samples 20 --workers 1 2 4" > /tmp/tti-synthetic-baseline-b.json
```

Run sequentially. Both slow invocations generate both sizes and seeds 137/271; compare
runtime, revision, locks, seed, source SHA-256/bytes/counts, workers and sample metadata
before comparing results. Default slow settings are one discarded warmup and five retained
samples, workers 1/2; this is smoke sampling, with p95 equal to the maximum. Twenty retained
samples make nearest-rank p95 the nineteenth ordered observation. Use at least twenty for
candidate disposition; report variability across both independent runs. Do not select the
fastest trial. Do not run under coverage, xdist, concurrent builds/tests or other imports.
Use AC power, disclose power mode, CPU/RAM, OS, toolchain and competing workloads. The
report records CPU model, physical memory, logical CPUs, architecture, OS release, Python,
Node/npm, DuckDB, commit and lock hashes. A dirty worktree is disclosed.

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

Each warmup/sample starts a new official `python -m app.ingest.run ... --workers N
--report-json` subprocess with owned DB, state and shard paths. Legacy fallback is disabled.
The outer wall timer spans process launch through exit: syntax validation, byte scanning,
reconciliation, final compatibility gate, fsync/swap, profile, manifest activation and
process shutdown. It deliberately does not trust the coordinator's earlier `total` field.
The subsequent benchmark parity verification is outside that timer. Generation and the
frontend build are also outside it. Rows/s uses all nine table row counts divided by that
full wall duration; it is not just top-level XML records/s.

Every trial, including warmups, verifies V2 mode/worker count, all nine exact table counts,
active/report generation identity, six child-parent anti-joins, known step sum and workout
duration sum. The generator keeps these health-value oracles private. The tiny regression
also verifies the generated corpus at workers 1/2/4 and rejects broken child counts.
Import failure, fallback, wrong identity/parity, nonfinite observations, attempted network
or missing memory samples rejects the run rather than publishing partial success.

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

Each trial then starts a new workload process. It boots the real app lifespan, calls real
ASGI routes and denies socket connect/DNS, model startup/health/stop and inference via
injected gateway stubs. Child environment inherits only tool discovery/locale, discarding
user credentials, provider config and app paths. Unsupported chat returns a denied-provider
fallback. Deterministic/cached chat must never invoke the stub provider. Provider latency
is **unmeasured: no inference**, not a fabricated zero-duration model call.

Chat costs separately identify first request in a fresh app process, a distinct fresh
uncached deterministic question, an exact cache hit, and denied-provider fallback. Profile
call count is instrumented. Cold/warm local latest/ranked/paged/trend queries are timed
separately using new vs repeated DuckDB connections. HTTP runs before those local scans;
OS filesystem caches are not flushed or controlled. HTTP metrics include middleware,
validation, serialization, route state and query work but use in-process ASGI: they exclude
TCP/TLS/browser/transfer costs. Do not subtract unrelated query timings to invent pure
HTTP overhead or equate connection-cold with a cold disk.

The scripted dashboard mount requests nine resources concurrently (summary, workouts,
volume, steps, heart, sleep, stages, capabilities, status), followed by a warm repetition.
Counts describe **one scripted mount**, not observed browser effect behavior. Actual
week/month toggle counts and scope/cancellation behavior still require browser/component
measurement. `browser_evidence=unavailable_requires_browser_run` is an explicit harness
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

Latest/ranked/cursor-paged joins are exercised by production query helpers. The harness
captures their actual parameterized statements without editing queries.py and executes
real `EXPLAIN ANALYZE`; it does not assume DuckDB materializes complete aggregate subqueries.
`app.bench.workload.explain_workout_joins(conn)` returns raw synthetic plans for **private
scratch inspection only**; published JSON records only successful plan execution. For
follow-up, invoke it on the same generated corpus/worker matrix using the official import
entry point in disposable storage. Examine actual scan/aggregate cardinalities, filter
pushdown and time for latest, ranked and first/subsequent cursor pages, both broad and
selective dates/type/source filters. Add those parameter variants before a final join
optimization decision. Keep raw plans private; publish allowlisted numeric summaries.
Compare the unchanged query, a scratch filtered-aggregate variant and (only if still
justified) a scratch summary-table variant with exact result/order/null/unit parity.
Include any summary-build time/storage in full import costs. No production query or schema
change is authorized by this preparation alone.

All candidate rows below are **pending measurement**, including no-change dispositions.
Use identical seeds/counts/workers/toolchain and interleaved baseline/variant runs with
warmups, >=20 retained samples and two independent repetitions. State an acceptable
regression/noise margin before examining variant results, grounded in baseline variability.
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

## Preparation verification receipt

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
