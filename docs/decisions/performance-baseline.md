# Measured synthetic performance baseline — #179

**Frozen #179 measurement complete.** All figures below describe the measured source and scratch selection experiments, not subsequent production results. The selected #180/#181 implementation and its pending measured acceptance are tracked in [the ingestion receipt](performance-ingestion.md). Parent owns integrated review, quiet candidate/portfolio measurements, CI receipts and issue closure; the baseline is bundled with those ingestion candidates.

The [closed numeric evidence](performance-baseline-results.json) contains every primary configuration/run metric, spread, retained count, memory experiment, browser count and candidate disposition. No health rows/values, question text, SQL, parameters, plans, local paths, hostname or credentials are in that JSON. Raw scratch plans and generated data remain private on the local machine.

## Frozen source and reference conditions

- Measurement head: `859f89a405499ecef024fb8dde127a5f3d7c2f77`; analytics #208/dev `aef8b4b` is included. Both matrices have identical runtime/locks and `worktree_dirty=false`. The analytics dates, sleep/comparison behavior and cache-v6 contract are unchanged.
- Backend lock SHA-256: `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b`.
- Frontend lock SHA-256: `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c`.
- macOS 26.6.2 / Darwin 25.6.0, Apple M5, 10 logical CPUs, 32 GiB RAM; CPython 3.12.11, uv 0.8.17, DuckDB 1.5.4, Node 20.20.2/npm 10.8.2. Browser: installed Playwright 1.63.0, isolated Chrome 155.0.8059.85, real 390×844 viewport.
- Primary matrices ran sequentially on battery, 94% before / 86% after, low-power mode off. Background user apps were not stopped: T3 Code, ChatGPT/Claude, Chrome/Brave/Safari, Docker/Xcode, and messaging/editor/desktop utilities. Sanitized process/app inventories are in the private environment reports. Initial load averages were 1.52/1.83/2.19; final 2.32/2.45/2.71. Swap usage was about 2.8 GiB when inspected; RSS is not private physical memory.
- Later supplemental/browser work followed wake and power transition; the final observation is AC/95%, low-power mode off. Within each prototype pair the variants were measured together/interleaved; do not pool different power phases into one latency population. A temporary task-owned sleep assertion was used for the awake follow-up and remaining experiments, then released.
- Power-log and file-epoch audit confirms no sleep overlap in either primary matrix or the memory experiments. A first five-sample follow-up overlapped clamshell sleep and is archived, operationally excluded. Its replacement ran awake. The original primary-matrix outlier is retained; it is not explained away as sleep.

## Decision criteria declared before results

Criteria were committed at `f873a2073250c06682dcd3ecfb76107fa57f624a` before viewing the pilot. No benefit/noise threshold was loosened after results:

- Flag independent-run median drift >10% or p95 drift >15%, with a 5 ms absolute floor. A useful latency experiment needs ≥10% **and** ≥10 ms. Preserve all retained observations and show min/max/population standard deviation.
- #180/#181: the **isolated phase** must save ≥15% and ≥10 MiB, with the allocation contributing ≥5% of full importer tree peak. Reject >10% wall regression. This phase criterion is distinct from claiming a ≥15% whole-import improvement.
- #183 uses the inherited proposed 250 ms unrelated-writer target and an actual conversation/pending-write path. A controlled 500 ms profile barrier establishes lock scope; those times are not natural p95. Blocking until release selects the short-write-scope candidate even when normal latency is below target.
- #184 needs repeated immutable-generation profiling at ≥10 ms and ≥10% of normal chat. Exact hits must scan zero times. #186 has an exact budget: one volume request for a granularity-only toggle.
- #187 selects a bounded lazy-chart experiment if chart code is in initial static JS and ≥100 KiB of loaded function code is unused at chat ready. It does not establish a latency improvement. #188 needs ≥10× raw-row transfer inflation, numeric trend p95 ≥20 ms and a parity-preserving scratch aggregate meeting the latency margin.
- Workout joins have a 50 ms per-helper p95 reference selection budget, stricter than the unchanged tiny query ceiling of 500 ms. All roadmap/reference figures remain proposed guidance, not machine-independent SLAs or new CI gates.

## Commands, sample counts and exits

From the repository root, with `PATH=/opt/homebrew/opt/node@20/bin:$PATH` and `PYTEST_XDIST_AUTO_NUM_WORKERS=2`:

```sh
uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py tests/bench/test_workout_plan_variants.py --no-cov -n 2 -q
make check
make bench
/usr/bin/time -p make bench-synthetic BENCH_ARGS="--cases representative --seeds 137 --workers 1 --ingestion-warmups 0 --ingestion-samples 1" > /tmp/tti-179-measure-20261022/pilot.json
/usr/bin/time -p make bench-synthetic BENCH_ARGS="--workers 1 2 4" > /tmp/tti-179-measure-20261022/matrix-a.json
/usr/bin/time -p make bench-synthetic BENCH_ARGS="--workers 1 2 4" > /tmp/tti-179-measure-20261022/matrix-b.json
/usr/bin/time -p make bench-synthetic BENCH_ARGS="--cases representative --seeds 137 --workers 4 --ingestion-warmups 1 --ingestion-samples 5" > /tmp/tti-179-measure-20261022/repeat-137-worker4.json
```

- Focused regressions: exit 0, 22 passed. The added spread test failed first; the harness fixture was updated to consume cache v6. `make check`: exit 0. No full 725-test suite was rerun for this harness-only work.
- Initial `make bench`: exit 2, 10 passed/1 failed because an old conversation fixture lacked a bound generation. The fixture now uses the public embedded snapshot adapter and asserts a real miss then exact hit. Corrected `make bench`: exit 0, 11 passed; no ceilings changed.
- Final pilot: exit 0, 35.27 s end to end, one retained import and 20 retained +2 warmup workload processes. Full cost was practical under the predeclared 45-minute bound, so no size/seed/worker reduction was made.
- Matrices A/B: exits 0/0, 369.08/382.27 s, each 12 configurations: both sizes × seeds 137/271 × workers 1/2/4. Per configuration: 1 discarded +3 retained full imports, then 2 discarded +20 retained fresh workload processes against the final single parity-verified generation. Total primary cost: 96 official CLI imports and 528 workload processes, including warmups.
- Structural 14-case EXPLAIN pass measured 84.12 ms median in the pilot investigation. A call-count regression preceded deduplication. It now runs once/configuration after timed query work; every configuration records `plan_matrix_runs=1`. All 20 actual query/HTTP trials remain. The first retained process-wall observation honestly includes that structural pass.
- The first five-import follow-up exited 0 but overlapped clamshell sleep (334.91 s outer wall) and is archived. The awake replacement exited 0 in 57.98 s: five retained imports, median 4.817 s, max/p95 4.857 s, σ 0.026 s. Its timing never replaces the original n=3 maximum of 6.717 s.

Corpus recipe v1: small 2,048 records/64 workouts/28 days; representative 500,000 records/8,192 workouts/180 days, 107,598,125 XML bytes. Counts, known private sums, child relationships and generation identity passed in every import, with fallback disabled. Both seeds have equal counts/different content hashes; each seed hash matches across workers and repeats. Seeds and hashes are in the numeric evidence.

## Primary matrix results

Cells are **median / p95 / population σ**. Import wall is seconds; summed process-tree RSS is MiB. Each import cell has n=3, so its p95 is its maximum, not a calibrated tail guarantee.

| Case | Seed | Workers | A import s | B import s | A tree MiB | B tree MiB |
| --- | ---: | ---: | --- | --- | --- | --- |
| small | 137 | 1 | 0.24 / 0.24 / 0.00 | 0.24 / 0.24 / 0.00 | 123.48 / 123.59 / 0.06 | 123.14 / 123.38 / 0.53 |
| small | 137 | 2 | 0.35 / 0.40 / 0.02 | 0.35 / 0.35 / 0.00 | 210.55 / 211.30 / 1.85 | 209.83 / 210.69 / 0.47 |
| small | 137 | 4 | 0.40 / 0.41 / 0.00 | 0.40 / 0.40 / 0.00 | 312.78 / 336.62 / 11.91 | 417.61 / 417.64 / 44.33 |
| small | 271 | 1 | 0.24 / 0.24 / 0.00 | 0.24 / 0.24 / 0.00 | 123.39 / 124.52 / 0.82 | 122.50 / 122.91 / 0.21 |
| small | 271 | 2 | 0.40 / 0.40 / 0.01 | 0.35 / 0.40 / 0.02 | 204.94 / 210.36 / 3.27 | 204.50 / 206.88 / 1.13 |
| small | 271 | 4 | 0.39 / 0.41 / 0.01 | 0.40 / 0.40 / 0.00 | 310.59 / 413.14 / 49.94 | 416.77 / 417.38 / 50.01 |
| representative | 137 | 1 | 6.83 / 6.89 / 0.03 | 6.93 / 6.95 / 0.07 | 631.22 / 633.84 / 2.64 | 627.02 / 629.53 / 1.66 |
| representative | 137 | 2 | 5.53 / 5.56 / 0.03 | 5.58 / 5.63 / 0.05 | 881.20 / 881.75 / 1.76 | 877.66 / 881.94 / 3.38 |
| representative | 137 | 4 | 4.81 / 4.81 / 0.01 | 4.93 / 6.72 / 0.85 | 1198.08 / 1203.42 / 2.71 | 1201.45 / 1203.84 / 5.44 |
| representative | 271 | 1 | 6.90 / 6.90 / 0.01 | 6.92 / 7.12 / 0.11 | 631.28 / 633.66 / 1.94 | 628.70 / 629.66 / 2.14 |
| representative | 271 | 2 | 5.49 / 5.53 / 0.02 | 5.69 / 6.14 / 0.24 | 878.48 / 883.02 / 2.21 | 882.77 / 882.78 / 2.49 |
| representative | 271 | 4 | 4.82 / 4.91 / 0.05 | 5.02 / 5.12 / 0.07 | 1198.86 / 1202.27 / 1.78 | 1207.81 / 1212.27 / 13.13 |

Every ASGI/query cell in the numeric evidence has n=20 per run/configuration. Representative results below show the range of medians and per-cell p95 values across both seeds/workers/repeats; these ranges are **not pooled quantiles**:

| Metric | Median range ms | Per-cell p95 range ms | σ range ms |
| --- | --- | --- | --- |
| `chat_http_cold` | 18.28–19.47 | 19.02–41.76 | 0.35–17.54 |
| `chat_http_fresh` | 14.04–14.96 | 14.73–39.03 | 0.36–7.31 |
| `chat_http_distinct_fresh` | 13.59–14.76 | 14.58–33.21 | 0.39–5.76 |
| `chat_http_cached` | 8.22–8.80 | 8.60–12.95 | 0.17–3.42 |
| `dashboard_http_cold` | 160.38–176.24 | 169.46–274.38 | 4.07–44.17 |
| `dashboard_http_warm` | 135.97–146.62 | 144.88–224.45 | 5.01–28.94 |
| `query_latest_cold` | 2.38–2.57 | 2.53–3.64 | 0.07–0.90 |
| `query_ranked_cold` | 2.33–2.70 | 4.56–37.02 | 2.19–17.58 |
| `query_paged_cold` | 2.15–2.28 | 2.25–3.18 | 0.07–0.36 |
| `query_trend_cold` | 106.48–110.23 | 108.15–168.86 | 1.08–19.64 |

All request scenarios retained the same generation, fresh app state and cache checks; exact hits scanned zero times. The standard five-request workload recorded four profile scans (cold, forced fresh, distinct fresh, denied fallback), zero real provider/network calls and provider latency **unmeasured**. HTTP is in-process ASGI; cold chat means first request after lifespan startup, not cold disk or server-startup latency. Process-wall metrics separately include startup/recovery/projection, requests, queries and shutdown.

Repeatability screening flagged 36 metric/stat comparisons under the declared drift rule, predominantly small p95 tails. All are retained in the evidence. Representative import medians, the large numeric-trend mechanism, request counts and candidate memory effects remain decisive; no useful-gain threshold was changed to dismiss noise. The single import-tail question received the bounded five-sample follow-up described above.

Calibration from observed data only: worker 1 minimizes representative RSS (~631 MiB) but costs ~6.8 s; worker 2 costs ~5.5 s/~880 MiB; worker 4 costs ~4.8 s/~1,200 MiB with the retained tail outlier. A **proposed reference tracking envelope** for this exact corpus is 2 workers, ≤6.5 s, ≤1 GiB sampled RSS and ≥100k total table rows/s. It is capacity-planning guidance with roughly observed-noise/headroom allowance, not a CI gate/SLA, not a default-worker change, and was not used to invent no-go decisions. Small exports favor one worker because process startup dominates.

## Supplemental mechanisms and browser

An additional representative/137/worker-1 official import supplies one persistent parity-verified synthetic store for all supplemental query, contention and browser work. Generating private oracles did not multiply official imports. Scratch prototype subprocesses never wrote production module files.

| Memory experiment | Baseline median MiB | Scratch median MiB | Reduction | Full wall median ms baseline → scratch |
| --- | ---: | ---: | ---: | --- |
| XML well-formedness phase | 94.23 | 32.23 | 65.79% | 615.37 → 620.85 |
| Full official import: validation cleanup | 630.08 | 543.59 | 13.73% | 7017.31 → 7015.00 |
| Full official import: bounded range | 630.08 | 524.70 | 16.72% | 7017.31 → 6950.96 |

Memory variants were interleaved/rotated, one warmup +3 retained processes each; n=3 peak p95 remains a maximum. Nested/malformed/truncated/wrong-root acceptance matched in four bounded cases. Full prototype imports preserved all counts/private sums/child joins. Copy-versus-bounded range kernels at 1/2/4 workers matched 508,372 parent elements and per-range byte digests, including nonzero bounds; tree-RSS medians were 350.31→247.91, 399.88→297.20 and 498.58→395.30 MiB. These are scratch selection experiments, not a claim that production is already optimized; full candidate implementation still needs official 1/2/4-worker parity and release gates.

| Conversation experiment | Median / p95 / σ ms | Retained samples / scans |
| --- | --- | --- |
| Natural conversation chat | 13.42 / 13.94 / 0.31 | 20 / 20 |
| Independent unrelated writer | 4.40 / 4.65 / 0.15 | 20 |
| Actual dataset profile | 2.86 / 3.00 / 0.11 | 20 / 20 |
| Scratch profile-reuse chat | 10.81 / 11.91 / 0.53 | 20 / 0 |
| Exact conversation hit | 7.26 / 7.65 / 0.34 | 20 / 0 |

These requests create actual conversations/pending turns. The independent writer creates an unrelated conversation on a separate connection after profile entry; it is not a GET/read-only baseline. The scratch profile reuse preserved sampled data/narrative envelopes and saved only 2.61 ms median. Exact cache lookup bypassed profiling in every request, including warmups. Normal writer p95 was 4.65 ms, below the proposed 250 ms target.

The separate causal diagnostic held profile preparation for an injected 500 ms, with bounded timeouts. In 3/3 trials the unrelated writer could not complete before release and completed afterward; observed diagnostic writer median/p95 was 574.11/575.63 ms. These are **injected barrier observations, not natural chat/writer p95**. They prove that the conversation write lock spans preparation.

Numeric trend prototype: three independent processes per variant, each two warmups +20 retained queries (60 latency observations/variant; three process-memory observations). Private weekly-step series parity held on every trial. Python transferred 125,000 observations to produce 26 buckets: median/p95/σ 106.29/108.90/1.35 ms. The scratch, fixed-Singapore weekly SUM query transferred 26 rows: 1.65/2.24/0.29 ms; process RSS 102.52→80.81 MiB. This establishes a hotspot and bounded prototype benefit, not general day/month/AVG/DST correctness or an adopted SQL rewrite.

Private plans: DuckDB 1.5.4 native JSON ANALYZE was first verified with a bounded SELECT probe. All 14 actual production-helper broad/selective/real-cursor variants showed 73,728 statistics scan rows (three scans of 24,576) and two aggregate outputs of 8,192 groups, even for selective windows. This is observed operator evidence, not source-code inference. Raw SQL/parameters/plan JSON/text remain private. The core report keeps operator cardinalities null; the separate validated numeric supplement records actual fields from this verified version. Despite full aggregates, every primary latest/ranked/paged p95 was below 50 ms (worst 44.04 ms), and median work was only a few milliseconds.

Browser: production build on an owned loopback server; isolated Chrome contexts, 2 warmups +20 retained scenarios. Provider completion/socket/DNS calls are denied. Optional readiness/status/health probes are stubbed truthfully unavailable, never real model probes. The first warmup aborted because setup counters had conflated blocked readiness with socket attempts (exit 1); the corrected setup is a separate complete run (exit 0), with zero provider calls, socket/DNS attempts, page errors and failed dashboard requests. The last context had four explicitly denied readiness probes. Only this task’s verified listener was stopped.

| Actual browser metric | Median / p95 / σ ms | Definition |
| --- | --- | --- |
| `cold_chat_ready_ms` | 94.20 / 97.20 / 4.40 | Fresh browser context/navigation → visible chat input +2 animation frames; browser process/OS are warm. |
| `first_chart_canvas_ms` | 196.15 / 196.90 / 3.26 | Submit → first visible nonzero chart canvas +2 frames; not animation completion. |
| `cached_chat_shell_ms` | 59.75 / 60.80 / 1.27 | Tab back → visible chat input +2 frames; not restored transcript paint. |
| `cached_dashboard_ms` | 140.95 / 149.40 / 8.26 | Return to previously loaded dashboard module → visible canvas +2 frames; panel HTTP requests still occur. |

Every retained scenario observed **9 initial dashboard resources** (status +8 panels), **8 week→month toggle requests** (all panels, status zero), **8 scoped-period requests**, and **9 resources on cached dashboard remount**. Counts were constant (σ=0). No unrelated ASGI/query latency was subtracted to fabricate TCP overhead; these are real browser/loopback end-to-end measurements with the definitions above.

Initial production JS: **1,381,072 bytes raw /456,513 bytes computed gzip**, one static entry chunk. Gzip is an artifact calculation, not a claim about server transfer encoding. A separate CDP coverage pass (not timed) found **1,082,062 initially loaded function bytes unused at chat ready**. An equivalent initial-entry source map, verified equal apart from source-map trailer/chunk hash literals, contains **487 ECharts module sources**. Unused bytes cover the whole entry, not an invented per-library gzip attribution. This selects lazy-boundary investigation but proves no post-change latency improvement.

## Candidate decisions and next constraints

| Candidate | Decision | Measured rationale and concrete trigger/next check |
| --- | --- | --- |
| #180 validation cleanup | **GO** | Isolated phase RSS −65.8%/62 MiB; full-import −86.5 MiB/13.7%, establishing >5% importer contribution. It meets the declared **phase** criterion; do not call 13.7% a ≥15% whole-import gain. Wall tradeoff is below 1%. Implement narrow sibling cleanup, then malformed/nested/activation and 1/2/4-worker parity/coverage gates. |
| #181 worker-range copies | **GO** | Range kernels save 103 MiB across 1/2/4 with identical byte oracles; full worker-1 import peak −105.4 MiB/16.7%, no material wall regression. Implement bounded mmap matching; verify real nonzero ranges, all typed/child rows/IDs and full worker matrix before claiming production benefit. |
| #183 short write scopes | **GO** | Actual pending-turn transaction blocks unrelated writes until a slow-profile barrier releases (3/3), despite normal 4.65 ms writer p95. Select the lock-scope fix for bounded responsiveness; do not claim the injected ~575 ms as natural p95 or an existing natural 250 ms failure. Preserve terminal-once/cancel/cache/history semantics. |
| #184 profile reuse | **NO-GO now** | Profile median/p95 2.86/3.00 ms; scratch reuse saves only 2.61 ms chat median, below the predeclared 10 ms floor, while exact hits already scan zero and normal chat is ~13 ms. Retain current safe identity behavior. Reopen if measured profile time reaches ≥10 ms and ≥10% of chat, or a larger/request-heavier corpus shows a qualifying gain. |
| #186 volume-only toggle | **GO** | Real browser n=20 sends eight panels for a volume-only toggle versus the exact one-volume budget (seven unnecessary requests); source/scoped refresh must still refresh all appropriate panels. Implement the narrow effect split with stale/cancel/loading/error tests. |
| #187 defer chart code | **GO** | Initial bundle contains 487 ECharts sources; 1.08 MB function code is unused at chat ready (>100 KiB criterion). Cold chat/first canvas/cached navigation are measured. Implement lazy boundaries and compare initial bytes plus first-use/error/fallback states; no latency gain is claimed yet. |
| #188 SQL numeric buckets | **GO** | 125,000→26 transferred rows, parity-preserving scratch weekly SUM 106.29→1.65 ms median (98.4%); RSS 102.5→80.8 MiB. Implement through the validated query/registry boundary with complete day/week/month, SUM/AVG, DST/offset, sparse/null/zero/unit oracles. Do not change sleep interval-union semantics. |
| Filtered workout aggregates / import summary table | **NO-GO now** | Actual plans show full aggregates but all primary per-helper p95 values meet the predeclared 50 ms reference budget; few-ms medians cannot yield a ≥10 ms median gain even if eliminated. Avoid import/storage complexity now. Reopen at sustained p95 >50 ms or roughly 10× workout/statistics volume, then benchmark a filtered aggregate before considering a summary table. |

## Private artifacts, commands and limitations

Local artifact root: `/tmp/tti-179-measure-20261022/`. Primary reports: `matrix-a.json`, `matrix-b.json`, `pilot.json`; valid follow-up `repeat-137-worker4.json`; archived invalid follow-up `repeat-137-worker4-sleep-overlap.json`. Each has a companion `.log`. Additional reports are `memory-candidates.json`, `contention.json`, `trend-prototype.json`, `plan-cardinalities.json`, `browser.json`, `bundle-graph.json`, `repeatability-flags.json`, `sleep-audit.json`, and sanitized `environment-*.json`. Their hashes and the private method-script hashes are in the closed evidence; do not publish the private corpus, DB, oracles or plan contents.

Supplemental commands (from backend via `uv run --directory backend`, scripts are at that local root):

```sh
uv run --directory backend python /tmp/tti-179-measure-20261022/run_experiments.py
uv run --directory backend python /tmp/tti-179-measure-20261022/experiments-pre-browser-fix.py contention
uv run --directory backend python /tmp/tti-179-measure-20261022/run_trend.py
uv run --directory backend python /tmp/tti-179-measure-20261022/experiments-pre-browser-fix.py plans
uv run --directory backend python /tmp/tti-179-measure-20261022/launch_server.py
node /tmp/tti-179-measure-20261022/browser.mjs
npm --prefix frontend run build -- --manifest --sourcemap --outDir /tmp/tti-179-measure-20261022/bundle-map
uv run --directory backend python /tmp/tti-179-measure-20261022/publish.py
```

All supplemental commands above exited 0 in their completed measurement runs. The memory experiment uses the exact archived `experiments-memory-version.py` implementation; the driver’s `experiments.py` pathname must point to that version for a byte-identical replay. Trend/plans used the pre-browser-readiness version; server/browser used the corrected readiness stubs. These private snapshots are hashed, and the current script retains the same candidate methods. The 14 original plan cases and independent import/workload counts remain reproducible through the committed root harness.

Memory method: `/bin/ps -axo pid=,ppid=,rss=` samples the importer parent and recursive descendants at 50 ms plus snapshot time. Convert KiB→bytes and take the maximum **simultaneous sum**, not independent per-process peaks. RSS double-counts shared pages and can miss short peaks; it is a sampled lower bound, not PSS/USS or true hardware memory consumption. The monitor itself is excluded. Full wall spans CLI process start through exit, including XML validation, reconciliation, compatibility, immutable activation/projection and ownership recovery. Extra harness oracle verification, XML generation and frontend build are outside that import timer.

No raw health record, real export, secret or live inference was used. No production query/schema/coordinator/byte-scan/API/dashboard/frontend optimization was implemented. Sampling, coverage and CI thresholds were not weakened. Data/docs-only publication follows measurement, so the final documentation commit differs from the frozen measurement head; both report headers still identify the exact measured code. Selected implementations and their post-change correctness/performance comparison remain future work, not unfinished baseline decisions. Parent owns batching, integrated review/browser outcome gates, CI monitoring, merge and issue closure.
