# Production performance portfolio — pre-main candidate #189

**BLOCKED: #187 first-use chart regression.** Actual first visible nonzero canvas +2 animation frames changes **179.60/196.20→479.20/495.90 ms** median/p95 (20 retained trials/head). Candidate minimum 461.70 ms exceeds reference maximum 196.20 ms. #189 is not accepted; no merged-main acceptance is claimed.

[Closed numeric evidence](performance-portfolio-results.json) contains all cells, counts, median/p95/min/max/population σ, criteria, dispositions and report/method hashes. It excludes health rows/values, questions, SQL/plans/parameters, paths and generation identifiers. Matrix cases contain ASGI/query/import evidence; `browser` contains real loopback TCP evidence.

## Identity and conditions

- Reference **`859f89a405499ecef024fb8dde127a5f3d7c2f77`**; integrated candidate **`51bc6dcc4c0b57768fcfcb50bc70387707f29209`** ([#209](https://github.com/Collaboration95/talktoit/pull/209), [#210](https://github.com/Collaboration95/talktoit/pull/210), [#211](https://github.com/Collaboration95/talktoit/pull/211)). Accepted matrices have clean worktrees.
- Frozen #179/4c451b1 evidence remains unchanged: numeric SHA-256 `e9259eeb5b4b7a4702911ce75287a65e8524fe59cec30c42e3b56625209101fe`. Old battery matrices/later AC supplements are not pooled here.
- Matching backend/frontend lock hashes: `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b` / `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c`.
- Apple M5, 10 CPUs, 32 GiB; macOS 26.6.2/Darwin 25.6.0; Python 3.12.11, DuckDB 1.5.4, Node 20.20.2/npm 10.8.2; Playwright 1.63.0/isolated Chrome 155.0.8059.85, verified 390×844 viewport without overflow.
- Every power checkpoint: AC/95%, low-power off. Owned idle-sleep assertion; 29.18-minute window, zero sleep/wake events or battery-power mentions. Both owned servers/assertion were stopped and parent notified immediately.
- Desktop apps remained open: T3 Code, ChatGPT, Brave/Safari, Docker/Xcode, messaging/editor/utilities. Initial load 2.33/2.09/2.35; sanitized CPU/RSS/process/app checkpoints are in JSON. Background load, thermal/frequency state and OS caches remain uncontrolled.

Initial reference exited 0 with parity but reported untracked dependency symlinks. Its complete `reference-setup-dirty.json` is archived. Links were moved inside real ignored tool directories without tracked edits. Accepted matrix order became **candidate→clean reference**, command wall 340.08/379.91 s. Phase pairs rotate order; contention/browser pairs run reference→candidate. No run was selected by timing.

## Sampling and imports

Each matrix: small/representative × seeds 137/271 × workers 1/2/4; per configuration **imports 3 retained +1 discarded**, workloads **20 retained +2 discarded** against one verified immutable generation. Combined: 96 imports/72 retained; 528 workload processes/480 retained. Every import verifies activation identity, nine-table counts, private known sums and orphan relationships. Workloads have fresh app state/cache and denied providers. Fourteen broad/selective/real-cursor production EXPLAIN variants run once/configuration.

Unchanged thresholds: useful latency ≥10% and ≥10 ms; median/p95 drift >10%/>15% with 5 ms floor; isolated memory ≥15% and ≥10 MiB, ≥5% importer contribution; ≤10% median import-wall regression. Writer reference 250 ms; toggle budget one request; workout p95 reference 50 ms. No new CI/SLA budget.

Cells are **median /p95 /population σ**. Wall seconds, summed tree RSS MiB; **n=3 p95=max**, reference-only. All per-cell throughput is in JSON.

| Case /seed /workers | Reference import s | Candidate import s | Reference RSS MiB | Candidate RSS MiB |
| --- | --- | --- | --- | --- |
| small /137 /1 | 0.24 / 0.24 / 0.00 | 0.24 / 0.24 / 0.00 | 122.67 / 123.17 / 0.28 | 123.09 / 123.80 / 0.40 |
| small /137 /2 | 0.35 / 0.35 / 0.00 | 0.40 / 0.41 / 0.00 | 211.39 / 211.84 / 0.31 | 210.42 / 210.88 / 1.39 |
| small /137 /4 | 0.40 / 0.40 / 0.00 | 0.41 / 0.41 / 0.00 | 311.14 / 321.02 / 5.07 | 316.86 / 421.23 / 50.39 |
| small /271 /1 | 0.24 / 0.24 / 0.00 | 0.24 / 0.29 / 0.02 | 122.81 / 123.70 / 0.43 | 122.53 / 122.80 / 0.47 |
| small /271 /2 | 0.40 / 0.40 / 0.02 | 0.40 / 0.40 / 0.00 | 210.67 / 211.31 / 4.09 | 210.38 / 211.72 / 3.16 |
| small /271 /4 | 0.60 / 0.66 / 0.06 | 0.40 / 0.45 / 0.02 | 423.00 / 423.41 / 38.81 | 421.73 / 423.14 / 0.68 |
| representative /137 /1 | 6.97 / 7.04 / 0.05 | 7.18 / 7.39 / 0.13 | 629.05 / 632.66 / 2.01 | 451.69 / 459.58 / 3.92 |
| representative /137 /2 | 5.58 / 5.60 / 0.01 | 5.87 / 5.88 / 0.11 | 882.03 / 884.47 / 2.54 | 715.97 / 716.58 / 1.58 |
| representative /137 /4 | 4.91 / 4.95 / 0.04 | 5.05 / 5.07 / 0.03 | 1188.64 / 1202.33 / 7.19 | 1030.86 / 1038.27 / 11.63 |
| representative /271 /1 | 6.84 / 6.90 / 0.04 | 6.97 / 6.99 / 0.03 | 629.33 / 634.59 / 2.60 | 455.27 / 457.61 / 2.48 |
| representative /271 /2 | 5.62 / 5.73 / 0.07 | 5.67 / 5.98 / 0.15 | 878.67 / 884.08 / 3.00 | 714.09 / 715.19 / 2.03 |
| representative /271 /4 | 4.95 / 5.05 / 0.06 | 5.28 / 5.84 / 0.33 | 1201.94 / 1202.08 / 0.49 | 1032.48 / 1037.91 / 8.21 |

Representative RSS decreases **13.3–28.2%**; wall medians increase **0.95–6.67%**, within 10%. Median throughput **96,682–137,336→93,914–133,602 rows/s**. The inherited proposed two-worker envelope (≤6.5 s/≤1 GiB/≥100k rows/s) holds here.

Small/137/2 initially flagged 349.50→403.05 ms (+15.3%). Interleaved **1 warmup +7 retained imports/head**, all parity-verified, measured **348.91/402.09→351.19/403.90 ms** median/p95 (+0.65% median). Both groups and every outlier remain separate. Roughly 50 ms subprocess wait/sampling granularity limits tiny-case comparisons.

Actual production phase helpers, representative seed 137/one worker, use 1 discarded +3 retained processes/head. Scan includes official parsing/reconciliation/oracle verification, excluding syntax validation; no prototypes.

| Production phase | Reference wall ms | Candidate wall ms | Reference peak MiB | Candidate peak MiB |
| --- | --- | --- | --- | --- |
| XML syntax validation | 612.42 / 620.98 / 21.13 | 623.45 / 626.15 / 1.77 | 93.23 / 93.27 / 0.66 | 30.92 / 30.97 / 0.02 |
| Scan/reconcile without syntax pass | 6039.54 / 6084.38 / 48.69 | 6017.15 / 6125.03 / 63.04 | 547.50 / 550.42 / 2.72 | 445.23 / 445.50 / 2.17 |

Validation saves **66.8%/62.31 MiB**, wall +1.8%; scan saves **18.7%/102.27 MiB**, wall −0.37%. Each exceeds 5% of full importer peak; phase savings are not additive combined-peak estimates.

Full wall includes CLI startup, syntax, compatibility, reconciliation, immutable activation and ownership recovery; generation/build/extra oracles are outside. `ps` samples simultaneous parent+descendant RSS every 50 ms plus snapshot cost. Shared pages can be double-counted and short peaks missed; this is RSS, not PSS/USS. Phase adapters record three peak observations; inner snapshot counts are available only for matrix imports.

## HTTP, writes and production trends

Per-cell ASGI/query n=20. Representative median ranges, kept as separate cells: cold chat **18.61–18.88→19.66–19.89 ms**, exact chat **8.18–8.37→8.69–8.94 ms** (increases below the absolute noise floor); dashboard cold **162.42–167.09→98.00–101.63 ms**, warm **137.61–141.22→74.13–77.05 ms**. Full p95/variance is in JSON. ASGI/query costs are separate from browser/TCP; inference is **unmeasured**, actual provider/socket/DNS calls zero.

Natural conversations use two distinct uncached questions, independent SQLite writers, 2 discarded +20 retained trials/head. Barrier: injected 500 ms, 1 discarded +3 retained trials. Cells are ms, median/p95/σ.

| Actual conversation metric ms | Reference median /p95 /σ | Candidate median /p95 /σ |
| --- | --- | --- |
| Natural chat | 14.83 / 16.08 / 0.79 | 14.75 / 15.62 / 0.42 |
| Natural independent writer | 4.32 / 4.57 / 0.19 | 0.67 / 0.82 / 0.06 |
| Actual profile | 3.35 / 3.65 / 0.26 | 2.94 / 3.27 / 0.15 |
| Exact hit | 8.12 / 8.31 / 0.17 | 8.09 / 8.30 / 0.15 |
| Injected barrier writer | 565.74 / 568.11 / 1.14 | 1.45 / 1.55 / 0.11 |

Pending visibility and writers finishing before barrier release both change **0/3→3/3**. Turns terminate once; exact hits profile zero times. Injected times are not natural p95. Natural writers already met 250 ms; #183's ordering mechanism is demonstrated. Each head performs 20 profiles for 20 retained uncached requests.

Actual production `get_trend` transfers **125,000→26 rows**, full private-series parity: **106.42/109.44/1.34→5.79/8.35/1.19 ms** (94.6% median reduction), RSS **118.63→100.17 MiB**. Counts: three retained processes/head ×20 queries=60, 2 query warmups/process, one discarded process; three memory observations. Focused SUM/AVG/day/week/month/zero/missing/timezone/DST oracles pass. Actual workout-helper worst p95 **33.28→24.36 ms** stays below 50 ms; all structural plan variants succeed.

## Static graph and actual browser

Initial static JS **1,381,072/456,513→230,338/71,028 raw/gzip bytes** (−83.3%/−84.4%). Gzip: Python level 9, mtime=0, summed per static resource; prior frontend receipt used Node level 6. These are artifact sizes. Exact production-matching maps show **487→0 ECharts sources**, candidate wrapper/zrender zero. Separate untimed CDP unused function bytes **1,082,062→119,949**.

Each head: 2 discarded +20 retained fresh Chrome contexts, real synthetic loopback server, reset caches/conversations. Server/OS remain warm/uncontrolled. Per retained group: 80 explicitly denied readiness probes, zero actual provider/network/external calls, failed panel requests or page errors. No subtraction of unrelated timings to infer TCP overhead.

Browser cells are ms, median/p95/σ. Cold/cached chat end at visible input +2 frames; cached dashboard at first canvas +2 frames. Volume ends at response completion +2 frames. Animation completion and physical-phone acceptance are unmeasured.

| Browser metric | Reference | Candidate |
| --- | --- | --- |
| Cold chat | 95.25 / 97.30 / 2.29 | 61.45 / 66.20 / 2.57 |
| **First chart: BLOCKED** | 179.60 / 196.20 / 7.25 | 479.20 / 495.90 / 9.82 |
| Cached chat shell | 60.20 / 61.00 / 0.99 | 59.00 / 60.40 / 0.72 |
| Cached dashboard canvas | 149.20 / 150.10 / 7.15 | 132.55 / 148.30 / 25.26 |
| Volume response +2 frames | 218.95 / 224.90 / 12.12 | 94.55 / 107.70 / 10.87 |

Constant relevant request counts (σ=0): **mount 9→9, toggle 8→1, scope 8→8, cached remount 9→9**; candidate toggle requests volume only.

One driver attempt exited 1 before scenarios: argument `label` collided with the panel-label function; code/log archived. Corrected locator run exited 0 but reported 196.30→912.95 ms first-chart medians. A 1+3 trace/head separated polling delay from actual canvas: candidate **478–481 ms**, reference **177–198 ms**, including two frames. Candidate scripts finished around 97–99 ms after submit; canvas appeared around 450–454 ms. Internal rendering cause remains unassigned.

Final 20+2/head collection timestamps first visible nonzero canvas per animation frame, then two frames, retaining the locator upper bound too. Both earlier runs/traces are archived; frozen evidence is unchanged. Actual first-chart regression **+166.8% median/+152.8% p95** exceeds the original margins.

## Dispositions

| Contract | Disposition at 51bc6dc | Evidence /reopening or completion trigger |
| --- | --- | --- |
| #180 | GO, retain measured change | Actual syntax memory/whole-import contribution criteria hold; preserve syntax and parity gates. Reopen for count/relationship drift or repeated >10% wall regression. |
| #181 | GO, retain measured change | Actual scan/reconcile memory criteria and 1/2/4-worker parity hold; bounded small-case follow-up resolves the initial wall flag. Reopen on reproducible >10% wall regression or lost/out-of-range rows. |
| #183 | GO, retain measured change | Committed pending turn visible and independent writer completes before release, 3/3; exact hits bypass profiles and terminal turns complete once. Reopen on ordering/cancel/terminal regressions. |
| #184 | NO-GO for added profile cache | Current profile median/p95 2.94/3.27 ms, exact scans zero. Reopen at ≥10 ms and ≥10% of natural chat, or a qualifying larger-corpus gain. |
| #186 | GO, retain measured change | Exact 9/1/8 counts and lower volume-response cost; reopen on extra toggle requests or stale scope/volume behavior. |
| #187 | **NO-GO for current candidate acceptance** | Initial graph/cold chat improve, but real first-chart regression is reproducible across all 20 retained trials. Frontend owner must resolve first-use rendering without losing the static graph/fallback guarantees, then repeat comparable browser trials within the original margins. |
| #188 | GO, retain measured change | Actual production transfer, parity, latency and RSS evidence hold; reopen for timezone/missingness/unit/output drift or loss of useful gain. |
| Workout join/summary table | NO-GO for new optimization | Current actual p95 meets 50 ms. Reopen at sustained >50 ms or roughly 10× workouts/statistics, then measure filtered aggregation before import-summary complexity. |
| #189 pre-main | **BLOCKED** | #187 criterion fails. This is candidate measurement qualification, not independent review or acceptance on merged main. |

## Commands, archives and remaining gates

Private `/tmp/tti-portfolio-20261022/` retains accepted matrices, dirty-setup archive, `production-phases.json`, head-specific contention/browser/locator/trace/graph reports, `small-followup.json`, command/environment/audit logs and hashed methods. Generated XML/DBs, raw series/envelopes, maps and SQL/plans remain private. Use disposable checkouts at the exact heads and matching tools/locks; adjust only archived drivers' local checkout paths.

```sh
# Matrix in each pinned checkout: exits 0/0.
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 make bench-synthetic BENCH_ARGS="--workers 1 2 4"
# Integrated candidate only: exit 0, 11 passed.
PATH=/opt/homebrew/opt/node@20/bin:$PATH make bench
# Concrete blocked first-chart reproducer after generated auxiliary setup:
PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-portfolio-20261022/run-browsers.py
# Focused evidence: exit 0, 270 passed.
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend pytest tests/bench/test_synthetic_harness.py tests/bench/test_synthetic_integration.py tests/bench/test_workout_plan_variants.py tests/integration/test_ingest_memory_contracts.py tests/integration/test_chat_write_scopes.py tests/integration/test_numeric_trend_sql.py -o addopts='' --no-cov -n 2 -q
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 make check
uv run --directory backend python /tmp/tti-portfolio-20261022/publish-portfolio.py
```

`make check` and publication exit **0**; publication validates closed types, grid/group counts, round trip, four negative privacy cases and frozen SHA. Original `run-supplements.py` exited **1** at browser syntax setup; phase/contention/map/graph children all **0**. Corrected locator/direct `run-browsers.py`: **0/0**; `run-chart-trace.py`/`followup-small.py`: **0/0**. Parent's exact #209/#210/#211 tiny-bench receipts are exit 0 and ten-green CI is parent-supplied; no CI was polled. No broad/full coverage gate was rerun for these evidence-only files, and no threshold/application behavior changed.

Parent still owns #187 repair plus comparable quiet requalification, final independent integrated review, accepted-candidate integration, and `make check-full`, coverage/bench, hosted CI and synthetic browser/lifecycle/outcome acceptance at the actual merged-main head. No future-main acceptance, PR creation, merge, issue closure or CI polling was performed here.
