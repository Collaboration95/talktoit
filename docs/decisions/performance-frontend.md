# Frontend request and chart boundaries — #186 / #187

The selected frontend changes are implemented and locally verified. Independent review,
quiet candidate/portfolio measurements, CI and integration remain with the parent.
No post-change latency or throughput gain is claimed.

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

`DeferredChart` contains Suspense and rendering/import errors around the chart alone.
It shares lazy component types by loader identity so an already-resolved chart does not
suspend again on a remount; its WeakMap stores component types, never chart props or
health records. Retry creates a fresh lazy type because React caches rejected loaders.
Chrome can also retain a failed module fetch: retry is an attempt, not a promise of
recovery. In an actual blocked-chunk check, retry remained failed and the formatted data
stayed usable. Trend failures expose a date/value table with shared formatters, preserving
null gaps and measured zero. Route failures retain metrics, GeoJSON download and Back.
The query and narrative live outside the boundary. Other answers and unknown-template
fallback remain available.

## Production graph and functional browser evidence

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

## Verification and remaining acceptance

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

Parent still must run `make bench` on quiet candidate heads, then comparable retained
before/after browser and portfolio trials using the baseline methodology. Report median,
p95 and spread for cold chat, first visible canvas (not animation completion), cached chat,
cached dashboard and volume latency; assess first-chart/cached-navigation regression
against retained noise. Independent review at the final integrated head, remote checks,
merge and post-merge acceptance are pending. Issues remain open and this is Review, not Done.
