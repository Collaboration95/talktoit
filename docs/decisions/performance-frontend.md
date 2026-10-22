# Frontend request and chart boundaries — #186 / #187

The original #211 implementation was merged, but the quiet integrated portfolio found a
blocking first-chart regression at `51bc6dc`. The chart-only repair below has local
correctness and mechanism evidence; comparable quiet browser requalification remains
pending. #187/#189 acceptance is not claimed. See the
[portfolio measurements](performance-portfolio.md) for the retained failure.

## Selection and retained baseline

All performance branches start from committed baseline/harness
`4c451b1c39507731b1bac652f034a6036b6848cb`, including analytics/dev `aef8b4b`.
The [baseline decision and definitions](performance-baseline.md) and
[closed results](performance-baseline-results.json) remain unchanged.

The baseline browser's 20 retained trials sent eight panel requests per volume-only
toggle, against the exact one-volume budget. Initial static JS was 1,381,072 bytes /
456,513 computed gzip bytes. At chat ready, 1,082,062 loaded function bytes were unused;
the static entry source map contained 487 ECharts sources. These observations selected
both changes. Baseline cold chat 94.20/97.20 ms and first canvas 196.15/196.90 ms are
median/p95 under the documented definitions, not animation-completion measurements.

## Request ownership

`DashboardView` loads training volume in its own effect keyed by scope, granularity,
whole-dashboard retry and volume-only retry. Each request has an AbortController and
captures the current scope generation. Both the callback and state updater reject stale
results, including adapters that ignore abort. A request-key check masks previous volume in the
selection commit itself, before passive effects clear it, so old totals cannot appear
under a new scope or granularity. Scope changes, saved-view application,
URL restoration and whole-dashboard retry still refresh all eight scoped panels;
status retains its independent lifecycle. A granularity-only change does not advance the
shared generation or cancel pagination and other panel requests.

The volume effect owns volume clearing/loading/failure. Its granularity controls remain
available during loading, empty results and errors. A failed volume request offers
`Retry training volume` inside that section; it does not invoke the shared retry or hide
other panels. Existing periods, filters, Reset, URL history, saved views and measured
sleep labels retain their tests.

## Chart boundaries and recovery

Only nonempty trends mount `LazyTrendLine`, which imports the existing `TrendLine`
renderer dynamically. Workout routes import the existing ECharts wrapper only when usable
geometry is displayed. Chart libraries, options, formatters and template dispatch remain
in place. Comparison currently renders a table and RankedList uses the existing custom
bars; neither needs a new lazy boundary. Existing tab laziness is preserved. No manual
chunk configuration or dependency/lock change is needed.

`DeferredChart` now uses explicit loading/ready/failed state around a shared module
promise, with the existing error boundary around the chart alone. Imports still start
only when the chart is used. The WeakMap stores import outcomes and component types,
never chart props or health records. Resolved components render immediately on remount;
active subscriptions ignore superseded/unmounted results and use current chart props.
Retry creates a new import resource and resets that chart's error boundary. Chrome can
retain a failed module fetch: retry is an attempt, not a promise of recovery. In an actual blocked-chunk check, retry remained failed and the formatted data
stayed usable. Trend failures expose a date/value table with shared formatters, preserving
null gaps and measured zero. Route failures retain metrics, GeoJSON download and Back.
The query and narrative live outside the boundary. Other answers and unknown-template
fallback remain available.

## Original #211 production graph and functional browser evidence

Node 20.20.2/npm 10.8.2, Python 3.12.11/uv 0.8.17; macOS, isolated Chrome
155.0.8059.85 via installed Playwright 1.63.0. All Vitest runs use at most two workers.
The user authorized Playwright fallback after two failed T3 preview attempts.

| Structural check | Baseline | Candidate |
| --- | ---: | ---: |
| Initial static JS bytes | 1,381,072 | 230,338 |
| Computed gzip bytes | 456,513 | 71,181 |
| ECharts sources in static entry | 487 | 0 |
| Granularity-only panel requests | 8 | 1 (volume) |
| Initial dashboard resources (status + panels) | 9 | 9 |
| Scoped-period panel requests | 8 | 8 |

Candidate bytes cover the manifest entry's recursive static JS imports, excluding
`dynamicImports`, CSS and source maps. Gzip uses Node `zlib.gzipSync` defaults, summed per
static JS resource, not server transfer encoding. A separate source-map build matches
production code after removing the map trailer; its initial closure contains zero
ECharts/wrapper/zrender and zero Chart.js sources. The deferred ECharts chunk remains
about 1.15 MB raw and triggers Vite's unchanged size warning. Bytes establish the
structural change only; first-use and cached-navigation latency remain pending.

Private artifacts and scripts: `/tmp/tti-frontend-performance-20261022/` contains
`graph.mjs`, `graph.json`, `functional.mjs`, `functional.json` and six inspected PNGs.
The functional script follows the private baseline browser/visual methods but records no
timings. It serves the real production build through an owned loopback Vite preview and
fulfills only explicit synthetic API fixtures in Playwright. All non-loopback traffic is
denied; there is no backend/provider process. These checks do not establish backend or
representative end-to-end latency. Viewports are 390×900 and 1440×900, with no horizontal
overflow; screenshots wait for chart loading and animations to settle.

The completed browser run (exit 0) checks:

- Cold chat requests only the static entry, and empty trends request no chart code.
- Delayed first chart import leaves the original query and sleep narrative visible;
  the first real canvas has nonzero dimensions.
- Comparisons preserve 0/7 and 3/7 coverage, missing values and neutral +2 bpm changes.
- Dashboard mount/toggle/scope send 9/1/8 relevant resources. A volume 503 plus its
  local retry send exactly two volume requests, preserving workouts and controls.
- Rapid toggle plus period change cannot replace the current 33-session volume with an
  old response. Request cancellation and an abort-ignoring adapter also have unit tests.
- A fresh context aborts the actual ECharts JavaScript chunk. Query, 150-minute value,
  missing bucket and zero-minute value remain visible; comparison and fallback still work.
- First-use route canvas/download/Back work. A separately failed route chunk preserves
  the GeoJSON download, metrics and navigation.
- No page errors, unexpected API requests or external requests occur. No provider is used.

The first functional-script attempt counted `/api/saved-views` as a dashboard resource and
failed its count assertion (exit 1); the counter was corrected to the documented nine
resources before the complete exit-0 run. No production assertion or budget changed.

## Original #211 verification

Regression tests preceded production changes: the original code failed the 16-vs-2
request assertion, loading-control availability and eager chart-import checks. The new
boundary initially failed import resolution because it did not yet exist. A later
cached-remount regression failed on a fresh loading state before component-type reuse
was added. Commit-time DOM inspection then exposed old volume totals under the new
month control before passive effects; that regression passed only after request-key
masking. All final assertions remain enabled.

Final local commands (repository root; set
`PATH=/opt/homebrew/opt/node@20/bin:$PATH`, `UV_PYTHON=3.12`,
`PYTEST_XDIST_AUTO_NUM_WORKERS=2`, `VITEST_MAX_WORKERS=2`):

```sh
npm --prefix frontend ci
uv sync --directory backend --dev --locked --python 3.12
npm --prefix frontend run test -- --run --maxWorkers=2 tests/components/dashboard-view.test.tsx tests/api/dashboard.test.ts tests/components/deferred-chart.test.tsx tests/components/lazy-trend-line.test.tsx tests/templates/chart-loading.test.tsx tests/components/template-dispatch.test.tsx tests/templates/trend-chart.test.tsx tests/templates/comparison.test.tsx tests/components/workout-detail.test.tsx
make test-frontend
npm --prefix frontend run test:coverage -- --maxWorkers=2
make lint-frontend typecheck-frontend check
npm --prefix frontend run build -- --manifest
npm --prefix frontend run build -- --manifest --sourcemap --outDir /tmp/tti-frontend-performance-20261022/bundle-map
node /tmp/tti-frontend-performance-20261022/graph.mjs
node /tmp/tti-frontend-performance-20261022/functional.mjs
```

All completed final commands exit 0: focused tests 81/81, full frontend 218/218;
coverage statements 89.14%, branches 80.30%, functions 91.28%, lines 91.99%.
Frontend 80/80/80/70 and backend global80/ingestion90/LLM70 gates are unchanged.
Backend source is unchanged beyond the required baseline ancestry; no full backend suite
or timed benchmark is repeated for this frontend patch. The first test invocation before
locked setup exited 127 (`vitest: command not found`); installation resolved it. Locked
npm install retains the baseline seven advisory findings; no dependency remediation is
claimed here.

The parent subsequently ran the quiet portfolio, including `make bench` and paired
browser trials. #186 retained its 9/1/8 counts; #187 failed first-use acceptance despite
its smaller entry. The original test/browser receipts above establish correctness and
static graph facts only. The current repair is documented next.

## First-use repair — 23 October 2026

Before edits, this branch fast-forwarded from `b568b31` to authenticated origin/dev
`e33545b3885542ed9e056c764d5339b5f369ef06`, which includes merged `51bc6dc` and the
portfolio evidence. Only `components/deferred-chart.tsx`, affected frontend tests and
this decision change in the repair. No provider, importer, chart library, preload policy,
shared documentation, lock, workflow or acceptance threshold changes.

### Confirmed mechanism

The parent's quiet n=20 result is retained unchanged: reference
`859f89a405499ecef024fb8dde127a5f3d7c2f77` versus `51bc6dc` first visible nonzero canvas
+2 frames **179.60/196.20 → 479.20/495.90 ms** median/p95. Locator polling's earlier
~912 ms observation is not the actual canvas metric.

A separate single instrumented production scenario on the pre-fix code identifies the
cause. CDP timeline timer stacks, resolved through the matching production source map,
point to locked React DOM's `react-dom-client.production.js:10804`. That call is inside
`performWorkOnRoot`'s `globalMostRecentFallbackTime + 300 - now()` / `"Throttled"` commit
path. The trace records a 298 ms timer, replacement 262 ms timer, then a 110 ms replacement
that actually fires at 371.9 ms after submission. The fallback appears at 70.0 ms and is
removed at 373.9 ms; scripts finish at 97.8 ms. This attributes the deferred reveal to the
React Suspense retry lane rather than assuming network transfer or locator delay.

`deferred-chart-reveal.test.tsx` was added and failed before the repair. It resolves a
controlled first import, lets normal React scheduled work run with only 32 ms of fake
clock advancement, and checks the accessible chart and retained query rather than an
internal timer or cache shape. It deliberately avoids `async act`, which eagerly flushes
Suspense retries and masked this problem in earlier tests. A second pre-fix failure
checks that an old import cannot replace a different current loader. The final tests
also preserve shared pending imports, current props, unmount protection, cached remounts,
loader/render errors, failed-retry recovery, real formatting and null/zero values.

The repair replaces only chart Suspense/lazy reveal with ordinary state updates after
an import promise settles. Existing dynamic import functions and chart options remain
unchanged. Tab Suspense stays in place. There is no eager import, hover/idle prefetch,
delay override, `flushSync` in production, animation change or library replacement.

### Diagnostic trace and functional evidence (nonqualifying)

The fixed single production trace has no timer stack in React's throttled commit path.
Scripts finish at 115.1 ms, loading is removed at 127.0 ms, and a first nonzero canvas
appears at 165.1 ms (+2 frames: 185.2 ms). The query remains visible. These are **single
instrumented mechanism observations while concurrent writers may run**, using explicit
synthetic browser-fulfilled APIs. They are not paired representative performance results,
not a speedup claim and not #187/#189 qualification. No import matrix or timed portfolio
was rerun.

Private receipts: `/tmp/tti-chart-repair-20261023/` contains `before-trace-private.json`,
`before-trace-summary.json`, `before-reveal-timers.json`, `after-trace-private.json`,
`after-trace-summary.json`, the private `trace.mjs` / `remap.mjs` drivers, and complete
command logs. The trace driver follows the portfolio's per-frame visibility definition
and adds CDP timer stacks and DOM loading/reveal markers. Its API fixtures isolate the
frontend mechanism; they do not measure the real backend/loopback request path.

Production manifest and matching source maps verify **230,763 raw /71,350 Node level-6
gzip bytes** in the initial static JS closure, with zero ECharts/wrapper/zrender or
Chart.js sources. The portfolio's Python level-9 gzip is a different calculation and is
not substituted here. Dynamic chart code remains outside that closure.

The full functional production-build browser script exits 0: no initial chart fetch,
empty/delayed first-use trend, query/narrative preservation, measured comparison coverage,
nulls and neutral deltas, unknown fallback, route first-use/download/Back and actual
failed chunk/retry all pass. Failed modules remain a truthful formatted-data/download
fallback if Chrome retains the failure. Dashboard mount/toggle/scope stays **9/1/8**;
volume failure plus local retry requests volume twice. There are no page errors,
unexpected API calls or external requests; no backend/provider process runs. The private
`functional.json` and phone/desktop PNGs accompany the copied functional driver.

### Repair verification and handoff

Node 20.20.2/npm 10.8.2, Python 3.12.11; use
`PATH=/opt/homebrew/opt/node@20/bin:$PATH`, `UV_PYTHON=3.12`,
`PYTEST_XDIST_AUTO_NUM_WORKERS=2` and `VITEST_MAX_WORKERS=2`.

```sh
npm --prefix frontend run test -- --run --maxWorkers=2 tests/components/deferred-chart-reveal.test.tsx tests/components/deferred-chart.test.tsx tests/components/lazy-trend-line.test.tsx tests/templates/chart-loading.test.tsx tests/templates/trend-chart.test.tsx tests/templates/comparison.test.tsx tests/components/workout-detail.test.tsx tests/components/template-dispatch.test.tsx tests/components/dashboard-view.test.tsx tests/api/dashboard.test.ts
npm --prefix frontend run test:coverage -- --maxWorkers=2
make check
npm --prefix frontend run build -- --manifest
npm --prefix frontend run build -- --manifest --sourcemap --outDir /tmp/tti-chart-repair-20261023/after
node /tmp/tti-chart-repair-20261023/graph.mjs
node /tmp/tti-chart-repair-20261023/trace.mjs after
node /tmp/tti-chart-repair-20261023/functional.mjs
```

All final commands exit **0**: focused **85/85**, full frontend coverage **222/222**.
Statements **89.28%**, branches **80.43%**, functions **91.36%**, lines **92.11%**; thresholds
and backend global80/ingestion90/LLM70 gates are unchanged. Before implementation the two
new regression files/cases exit **1** (two failures, three preexisting tests passing).
The pre-fix build/trace/remapping also exit 0 and remain separate diagnostic artifacts.

Parent owns the unchanged n=20 +2-warmup paired reference/fixed browser requalification
once concurrent writers stop, including cold chat, first visible canvas +2 frames,
cached navigation and request counts against the original margins. No full import matrix
rerun is required for this frontend-only patch. Parent will batch this branch with the
portable browser-gate follow-up; no standalone repair PR, CI polling, merge, issue closure
or independent review loop is performed by this child. #187/#189 remain pending until
quiet requalification and the parent's integrated acceptance pass.
