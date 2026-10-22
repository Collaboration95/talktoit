# Chat write scopes and numeric trend aggregation

This batch implements the selected #183 and #188 mechanisms and retains the
accepted **NO-GO** for #184. It starts from committed baseline
`4c451b1c39507731b1bac652f034a6036b6848cb`, including dev `aef8b4b` and #208's
sleep/comparison semantics. The [baseline decision](performance-baseline.md)
and [immutable numeric evidence](performance-baseline-results.json) remain the
authority for candidate selection. Their scratch measurements are not results
for this implementation.

## #183: commit pending turns before preparation

The initial SQLite session validates the conversation against the request's
existing leased dataset identity and inserts its pending turn. The session
commits before publishing the pending-turn handle and before profiling, local
planning, follow-up resolution or semantic candidate evaluation. Exact and
canonical lookups own short sessions: a cache read also updates hit counters,
so even a rejected cached envelope must commit that bookkeeping before slow
preparation resumes. Follow-up/candidate reads never join a write transaction.
Final cache writes and turn completion retain their existing atomic session.

The worker handle also identifies the committed turn if preparation raises
before returning its full state. Existing failure envelopes remain useful and
private; failure and cancellation use the repository's pending-only terminal
updates. Cancellation still waits for the shielded worker to settle so it
cannot abandon a late commit or close the request's DuckDB connection early.
The generation lease, provider behavior and HTTP/CLI orchestrator are unchanged.
No state/DB/lifecycle mutex is added around an await.

`test_chat_write_scopes.py` uses bounded threading-event barriers, real SQLite
connections and denied provider calls. It proves that an unrelated conversation
writer completes **before** profile/planner/candidate release, with the original
pending turn already visible. It covers success/cancellation, cancellation
before handle publication, cancellation followed by a preparation failure,
all existing preparation error classes, immutable terminal states, exact-cache
profile bypass and a rejected exact-cache envelope's bookkeeping transaction.
Timeouts bound a broken test; they are not new response-time budgets.

The baseline's natural unrelated-writer median/p95 was **4.40/4.65 ms**, already
below the proposed 250 ms reference target. Its separate injected 500 ms
profile barrier blocked that writer in 3/3 trials and produced a diagnostic
574.11/575.63 ms median/p95. Those diagnostic values are **not natural latency**.
This implementation establishes ordering through regression tests; comparable
candidate median/p95 measurements remain pending on the parent's quiet machine.

## #188: transfer numeric buckets from DuckDB

`get_trend` now binds metric, half-open UTC window, IANA timezone, granularity
and aggregation into a fixed SQL query. DuckDB attaches UTC to stored naive
timestamps, converts to local wall time, truncates by day/week/month, then
computes SUM or observation AVG. Python receives only bucket rows and retains
the existing ISO labels, ordered bucket generation and null gap filling.
Unit labels and existing raw-value semantics are retained; this batch adds no
conversion or new metric interpretation.

`test_numeric_trend_sql.py` freezes the pre-change Python observation-transfer,
zoneinfo-bucketing and accumulation algorithm as an independent oracle.
Cases cover Singapore ISO week-year and leap/month boundaries, New York DST
gap/fold, Kathmandu's fractional offset, Lord Howe's half-hour DST change,
half-open microsecond edges, SUM/AVG/default aggregation, known/unknown metric
metadata, mixed stored units, missing/null-only days, genuine zeros, empty input
and output ordering. Numeric comparisons allow only floating-point accumulation
roundoff (relative tolerance 1e-13); labels, nulls, zeros and metadata must agree.
A counting adapter around real DuckDB verifies 10,000 synthetic observations
produce one transferred weekly row with the expected total.

The shared sleep interval union, categorical sleep dispatch and metric
comparison calculation are unchanged. Existing sleep/dashboard/comparison and
HTTP/CLI parity tests remain part of surface verification; sleep is never
treated as a numeric average.

The selection prototype transferred **125,000 -> 26** rows and measured
106.29/108.90 -> 1.65/2.24 ms median/p95, with process RSS
102.52 -> 80.81 MiB. That scratch query covered fixed-Singapore weekly SUM only.
This general implementation has no measured speedup or RSS claim yet.

## #184: NO-GO, retain current profiling

The baseline's actual profile median/p95 was **2.86/3.00 ms** (20 retained
requests). Scratch reuse saved **2.61 ms** chat median, below the declared
**10 ms** useful-gain floor. Exact hits already scan zero times. Adding profile
cache identity, mutation, eviction and invalidation complexity is not justified
by that measurement. This batch keeps per-request profiles on uncached work;
a denied-provider regression checks two distinct fresh questions compute two
separate profiles. No profile cache or profile optimization is introduced.

Reopen only when repeated immutable-generation profiling measures **at least
10 ms and at least 10% of normal chat**, or a larger/request-heavier synthetic
corpus demonstrates a gain meeting the declared useful-gain criteria. Any later
proposal must independently preserve generation/CLI override isolation,
immutable concurrent results, bounded invalidation and exact-hit zero scans.

## Verification and remaining acceptance

Regression tests were written and run before feature changes. The old path
failed pending visibility and terminal-failure tests, and transferred 10,000
rows where one was required. A further rejected-cache barrier failed with an
unrelated writer blocked until release before its transaction-scope fix.

Runtime for candidate verification: Python 3.12.11 and Node 20.20.2. Pytest
auto workers are capped with `PYTEST_XDIST_AUTO_NUM_WORKERS=2`; any Vitest
verification uses `--maxWorkers=2`. Fixtures and storage are synthetic/local,
and providers are denied. No dependency or lockfile changes are included.

Local command results (all exit 0; final PR receipt includes the full selectors):

- Focused chat/cache/follow-up/conversation/cancel/snapshot/semantic and
  trend/sleep/comparison/CLI tests: **423 passed**.
- `make test-backend`: **983 passed**, **89.07%** overall coverage (80% gate).
- `uv run --directory backend coverage report --include='app/ingest/*' --fail-under=90`:
  **91.24%** (90% gate).
- `uv run --directory backend coverage report --include='app/llm/*' --fail-under=70`:
  **84.48%** (70% gate).
- `npm --prefix frontend run test -- --run --coverage --maxWorkers=2`:
  **208 passed**; statements **88.72%**, branches **79.78%**, functions **90.74%**,
  lines **91.73%**, with all existing thresholds retained.
- `make check`: backend format/lint/Pyright, frontend lint/types/format and version
  consistency all passed. These already include the backend lint/type gates.

Commands used `UV_PYTHON=3.12`, Node 20 on `PATH`, and the pytest worker cap above.
The full backend run used disposable `TTI_DB_PATH`/`TTI_APP_STATE_PATH` storage.
No broad gate was repeated after passing. `npm ci` used the committed lock and
reported the existing seven dependency advisories; dependency remediation remains
outside this batch's scope.

**Pending parent acceptance:** quiet `make bench` at candidate heads; comparable
before/after portfolio trials with natural/controlled writer median/p95,
numeric trend transfer counts, memory, median/p95 and output parity; final
independent review after all batch PRs; hosted CI, integration and post-merge
checks. These performance measurements are deliberately deferred while other
writers run. The parent integrates the baseline/ingestion batch first. This PR
is reviewable implementation evidence, not Done or issue-closure evidence.
