# Actual-main performance qualification — #189

**VERDICT: REVISE.** Main `a0ac51b6a24442f669608f153efe5b0c98931051` fails the unchanged cached-chat browser return margin in both the primary pair and one counterbalanced confirmation. Main also records failed panel requests, so the zero-error criterion is not met. All original observations remain; no outlier was removed, no threshold changed, and no source/optimization/dependency change was made. The parent must keep #189 open pending resolution or independent adjudication and requalification.

[Closed numeric report](main-performance-results.json) contains the exact source/lock/environment identities, all 624 normal matrix observations including warmups, phase/query/conversation/import/browser raw trials, summaries, comparison flags, artifact/method hashes and failed checks. Every published statistic is recomputed from those raw observations. Health rows/values, GPS, question text, SQL/plans, paths and generation IDs are excluded. Private synthetic oracles and raw child logs stay local.

## Blocking evidence and bounded reproduction

Milliseconds below are **median /nearest-rank p95 /population σ**, 2 discarded +20 retained scenarios/head. Cached chat means tab return to visible input +2 frames, including the original locator click; it does not mean restored-transcript paint.

| Cached-chat pair | Fresh reference | Actual main | Median /p95 increase |
| --- | --- | --- | --- |
| Primary reference→main | 58.30 / 69.90 / 8.35 | 69.20 / 84.50 / 10.12 | 18.70% /20.89% |
| Counterbalanced main→reference | 59.30 / 70.50 / 7.48 | 67.65 / 85.20 / 9.26 | 14.08% /20.85% |

Both median increases exceed 10% and both p95 increases exceed 15%, with differences above the original 5 ms floor. The same exact direct-frame method, source pair, generated corpus and current AC phase were used. The confirmation was bounded in advance to one additional pair; its result was not selected as a best run. Timed work stopped after the persistent failure. Source cause is **unassigned**; no production-code defect is inferred solely from the timing.

Main's primary retained trials contain **one** failed relevant panel request (raw trial 7); confirmation retained trials contain **three** (raw trials 5, 12, 20), plus one discarded-warmup failure (trial 2). Reference has zero in both pairs. The unchanged driver records counts but not endpoint/reason, so these are not classified as intentional aborts or hidden as harmless cancellation. All affected trials remain. Provider/socket/DNS/external calls and page-error counts are zero; panel-request failures still make the zero-error check fail.

A secondary primary-only flag is natural conversation-chat p95 **18.38→33.46 ms** (median 17.31→16.97 ms). It was not retested after the confirmed browser blocker triggered the stop rule. The ranked-query primary p95 flag **3.56→9.54 ms** did not reproduce beyond the absolute floor in its one exact-workload confirmation: **4.13→6.27 ms** (difference 2.14 ms). That group used one setup import/head and 2+20 fresh workload processes, not twenty full imports.

Exact executed reproducer: `PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-final-20261023/main-performance/latency-confirmation/run.py`, exit **0**. This runs the exact source checkouts, query confirmation and counterbalanced real browser scenarios. The acceptance predicates are false even though execution succeeds. To reproduce again, copy the archived drivers into a **fresh output directory**, change only their local output/checkout paths and retain exact source pins; do not overwrite these receipts.

## Source, compatible harness and conditions

- Main whole tree **`3de52384a0c216eaf597f9293e1eb9c3dda6a881`**. App/test trees: backend app `f75d9a0948217621e380a655fbe0560f3dcb23f3`, backend tests `5bfcff185625429808f0e8db68b9d296f6170c6d`, frontend source `9812124868edcd97694b01c31d8fae58d8a32dcb`, frontend tests `a77651bf117dbdff932e4299503ed061ee5390d1`.
- Fresh reference source **`859f89a405499ecef024fb8dde127a5f3d7c2f77`**. Both checkouts were clean at capture. The assigned worktree was detached at exact main; the parent checkout and untracked reports were not changed.
- Matching backend/frontend lock SHA-256: `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b` / `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c`.
- The production `app/bench` modules are byte-identical on the two heads. One off-checkout observation adapter delegates to the original process timer and returns its result unchanged, capturing numeric observations only **after** the child/timer finishes. Reference production implementation was not patched. Harness hashes and production-source hashes are separately recorded. Actual cache keys are reference v6/main v8.
- Apple M5, 10 logical CPUs, 32 GiB, macOS 26.6.2/Darwin 25.6.0; all product measurements Python 3.12.11, DuckDB 1.5.4, Node 20.20.2/npm 10.8.2. Real Chrome 155.0.8059.85 via installed Playwright 1.63.0; verified 390×844 viewport, no horizontal overflow. Static source maps match the production build.
- All power checkpoints are AC/95%, low-power off. Full 25.72-minute measurement-window audit found **zero sleep/wake events and zero battery-power mentions**. Desktop T3 Code, ChatGPT, browsers, Docker/Xcode, messaging/editor/utility apps remained open. Full sanitized load/app/CPU/RSS/process checkpoints are in JSON; this was a quiet delivery window, not an idle-machine guarantee.
- An owned idle-sleep assertion was started with the matrix controller. Its PID was already absent at final cleanup; continuous assertion after that controller exited is **unverified**, and is not claimed. Power logs independently show no sleep overlap. All owned servers/measurement jobs are stopped and no owned assertion remains. The parent was told the window was released before report generation.

The old 4c/859 baseline, failed 51bc portfolio and repaired a91 chart reports remain byte-identical and historical. Neither their battery runs nor their separate AC windows were pooled into this actual-main comparison. The earlier CDP diagnostic was not used for qualification. CDP here is an untimed code-coverage pass only.

## Normal matrices and import/recovery cost

Each source ran small/representative × seeds 137/271 × workers 1/2/4. Each configuration has **1 discarded +3 retained official imports**, then **2 discarded +20 retained workload processes** against one parity-verified immutable generation. Combined primary evidence: **96 imports/72 retained**, **528 workload processes/480 retained**. Every import, including warmups, checks public leased generation identity, nine-table counts, private known sums and child/orphan relations. Each cold workload starts fresh app state/cache; exact/fresh semantics and provider-denied fallback are checked. Structural 14-variant broad/selective/actual-cursor production plans run once/configuration.

Import cells are **median /p95 /σ seconds** and simultaneous tree RSS **MiB**; n=3 p95 is the maximum, reference-only. All throughput observations are in JSON.

| Case /seed /workers | Reference import s | Main import s | Reference RSS MiB | Main RSS MiB |
| --- | --- | --- | --- | --- |
| small /137 /1 | 0.26 / 0.26 / 0.00 | 0.30 / 0.31 / 0.02 | 123.00 / 123.02 / 0.45 | 122.98 / 123.14 / 0.65 |
| small /137 /2 | 0.41 / 0.42 / 0.02 | 0.41 / 0.43 / 0.01 | 211.45 / 261.66 / 24.99 | 261.72 / 261.83 / 0.15 |
| small /137 /4 | 0.44 / 0.48 / 0.03 | 0.48 / 0.49 / 0.01 | 419.08 / 422.17 / 2.01 | 406.27 / 414.69 / 10.78 |
| small /271 /1 | 0.29 / 0.31 / 0.03 | 0.25 / 0.26 / 0.00 | 122.97 / 123.20 / 0.31 | 122.83 / 123.66 / 0.81 |
| small /271 /2 | 0.41 / 0.42 / 0.01 | 0.43 / 0.44 / 0.00 | 208.39 / 261.42 / 25.08 | 261.59 / 261.73 / 0.10 |
| small /271 /4 | 0.42 / 0.47 / 0.02 | 0.48 / 0.49 / 0.03 | 422.33 / 422.59 / 0.55 | 404.52 / 422.81 / 8.76 |
| representative /137 /1 | 7.22 / 7.37 / 0.07 | 7.41 / 7.88 / 0.25 | 631.02 / 632.06 / 1.66 | 449.70 / 451.30 / 1.42 |
| representative /137 /2 | 5.89 / 5.89 / 0.02 | 6.09 / 6.13 / 0.02 | 881.28 / 882.77 / 0.85 | 716.16 / 718.55 / 2.66 |
| representative /137 /4 | 5.38 / 5.91 / 0.28 | 5.46 / 5.50 / 0.04 | 1198.64 / 1202.95 / 8.11 | 1036.41 / 1046.20 / 6.72 |
| representative /271 /1 | 7.41 / 7.41 / 0.04 | 7.42 / 7.53 / 0.09 | 628.66 / 633.89 / 2.95 | 454.89 / 462.06 / 4.11 |
| representative /271 /2 | 6.02 / 6.06 / 0.03 | 6.00 / 6.05 / 0.03 | 883.34 / 884.22 / 3.74 | 713.91 / 715.78 / 3.21 |
| representative /271 /4 | 5.54 / 5.55 / 0.07 | 5.38 / 5.42 / 0.05 | 1196.34 / 1198.23 / 0.99 | 1028.67 / 1049.61 / 15.76 |

Representative median RSS falls **13.53–28.73%**; full-wall median changes range **-2.91% to +3.40%**, within 10%. This includes current capture/hash/fsync/validation/private-disposal/recovery work through actual CLI exit, not the importer's earlier internal total. Corpus generation, frontend build and extra observer oracles are outside that timer.

Two short-import cells initially exceeded 10%; each received exactly one interleaved 1+7/head follow-up under the retained prior policy. Results remain separate, never replacing/combining primary counts:

| Small cell | Primary reference→main median ms | Follow-up reference→main median ms | Follow-up change |
| --- | --- | --- | --- |
| 137 /1 workers | 260.54→303.94 | 262.38→260.13 | -0.86% |
| 271 /4 workers | 421.23→481.72 | 430.59→435.58 | +1.16% |

The approximately 50 ms subprocess wait/sampling cadence limits tiny-case comparisons. All initial flags, maxima and follow-up observations remain available. Small two-worker RSS also rises in this sample; it is not presented as a universal memory reduction.

A separate **actual repeated-import** sequence/head uses two setup generations, one discarded warmup and three retained representative seed-137/two-worker imports. Every retained main import retires one older generation through the real protocol. Median/p95/σ wall: reference **6.03/6.11/0.05 s**, main **6.13/6.15/0.04 s** (+1.68% median). Two public recovery repetitions after every import verify the active identity (extra verification outside the import timer). Reference ends with six published DB payloads; main retains active/latest rollback only: **two**. Current inventory has **20 CLEANED claims, zero captured payload bytes**. Logical published DB sizes are 320,937,984 versus 107,765,760 bytes; these are file lengths, not physical block-use estimates. Empty metadata/directories/locks intentionally remain.

RSS uses `/bin/ps` every 50 ms plus snapshot cost, taking the maximum simultaneous parent+recursive-descendant sum. Shared pages can be counted repeatedly; short peaks missed. This is sampled RSS, not PSS/USS or a true hardware peak. Actual snapshot counts are retained for every process group.

## Current production phase, writer and query results

Phases use actual helpers without syntax bypass/prototype optimization. Scan means official coordinator parse + Parquet reconciliation/oracles, excluding syntax and activation; full CLI groups separately include lifecycle/disposal. Representative seed 137/one worker, 1 discarded +3 retained processes/head. Cells: **median /p95 /σ**, wall ms/RSS MiB.

| Phase | Reference wall | Main wall | Reference RSS | Main RSS |
| --- | --- | --- | --- | --- |
| XML syntax validation | 602.75 / 618.89 / 9.19 | 651.39 / 655.62 / 22.23 | 93.28 / 93.41 / 1.18 | 31.02 / 31.19 / 0.10 |
| Scan/reconcile | 6287.86 / 6409.74 / 61.34 | 6335.34 / 6390.75 / 28.62 | 543.00 / 544.55 / 0.83 | 443.34 / 443.64 / 2.08 |

XML phase saves **62.27 MiB/66.75%**, wall +8.07%; scan saves **99.66 MiB/18.35%**, wall +0.76%. Each memory saving exceeds 5% of the reference full importer peak and the original 15%/10 MiB isolated-phase thresholds. Phase savings are not additive whole-import estimates.

Actual conversation/pending-turn natural trials use two distinct fresh questions and independent SQLite writers: 2 warmups +20 retained/head. Exact hits profile zero times; distinct misses profile 20/20. Barrier trials: 1+3/head with a controlled injected 500 ms hold. Cells are ms, median/p95/σ.

| Conversation metric | Reference | Main |
| --- | --- | --- |
| Natural chat | 17.31 / 18.38 / 0.75 | 16.97 / 33.46 / 5.57 |
| Natural independent writer | 4.98 / 5.36 / 0.33 | 0.70 / 0.81 / 0.20 |
| Actual profile | 3.77 / 4.06 / 0.19 | 3.42 / 4.28 / 0.47 |
| Exact hit | 9.12 / 11.70 / 1.41 | 9.41 / 9.76 / 0.22 |
| Injected barrier writer | 602.91 / 604.68 / 5.19 | 0.90 / 1.31 / 0.20 |

Pending visibility and writers finishing before profile release change **0/3→3/3**; turns complete once. Injected barrier times are not natural p95. Natural writers already satisfy the 250 ms reference target. #184 profile caching remains NO-GO: current profile median/p95 **3.42/4.28 ms**, below the ≥10 ms AND ≥10%-of-chat reopening rule. Natural chat's higher primary p95 remains an additional unconfirmed flag; it was not discarded or retested after the browser stop condition.

Actual production numeric `get_trend` transfers **125,000→26 rows** with complete private-series parity. Three retained processes/head ×20 retained queries (two inner warmups/process), one outer discarded process: **60 query observations/head**, three peak-memory observations. Median/p95/σ **111.08/117.85/2.90→7.54/8.75/0.71 ms**; process RSS **119.72→100.52 MiB**. The 232 current focused tests pass independent frozen-Python day/week/month/SUM/AVG/DST/fractional-offset/null/zero oracles plus malformed/nested/range/legacy/V2/all-table worker-invariance controls. No sleep-interval rewrite or profile cache was added.

Workout helper worst primary p95 is reference **11.14 ms**, main **9.54 ms**, below the unchanged 50 ms reference selection budget. All 14 structural plans succeed with real next-page cursors. The separate summary-table/filtered-aggregate optimization stays NO-GO; reopen at sustained >50 ms or roughly 10× workouts/statistics, then measure before adding complexity.

## Actual production browser/graph

The final direct-frame method is retained: first nonzero visible canvas +two frames; locator upper bounds are diagnostic only. Cold chat is navigation→visible input +two frames; cached dashboard ends at observed visible canvas +two frames; volume ends at response completion +two frames. Browser contexts are fresh, servers/OS caches warm and uncontrolled. Real loopback TCP is separate from in-process ASGI/query costs; no subtraction invents TCP overhead. Inference latency and animation completion are unmeasured.

Primary pair cells are ms, median/p95/σ; each is 2+20/head.

| Browser metric | Fresh reference | Actual main |
| --- | --- | --- |
| Cold controls | 109.35 / 120.00 / 7.83 | 74.75 / 81.60 / 6.04 |
| First chart +two frames | 211.75 / 212.60 / 7.29 | 193.25 / 209.10 / 11.16 |
| Cached chat — FAIL | 58.30 / 69.90 / 8.35 | 69.20 / 84.50 / 10.12 |
| Cached dashboard | 149.20 / 149.90 / 3.75 | 149.10 / 149.50 / 11.48 |
| Volume completion | 215.50 / 232.40 / 17.38 | 94.90 / 114.70 / 11.61 |

Static closure **1,381,072/456,513→230,763/71,199 raw/gzip bytes**, production-matching maps **487→0 initial ECharts sources**, main wrapper/zrender zero. Gzip is Python level 9/mtime=0, summed per static JS resource, not measured transfer encoding. CDP runs separately without timed-scenario instrumentation. Relevant request counts are constant: reference/main mount **9/9**, toggle **8/1**, scope **8/8**, cached remount **9/9**. Main toggle requests volume only. Failed panel requests still fail the error criterion despite correct counts and zero provider/external/page-error counters.

## Criteria, commands, integrity and limits

| #189 criterion | Actual-main result |
| --- | --- |
| C1 identical cases and documented comparable setup | Fresh full matched matrices, production groups and browser pairs retained at exact heads/locks; no historical timings reused as current. |
| C2 justified improvement without material regression | **NOT MET:** cached-chat median/p95 regression reproduced; main has unclassified failed panel requests. Other selected memory/trend/request/static improvements and worker/value/timezone/missingness correctness are observed. |
| C3 bounded claims | Synthetic-only; no tiny fixture/full-personal-export, inference, animation, physical-phone, true-memory-peak or physical-power-loss guarantee. |
| C4 concrete failed-gate receipt | **REVISE**, gate remains open. Parent owns source/method adjudication, any correction, fresh qualification and independent actual-main acceptance. |

Unchanged thresholds throughout: useful gain ≥10% AND ≥10 ms; phase RSS ≥15% AND ≥10 MiB with ≥5% full-import contribution; median import-wall regression ≤10%; other median/p95 regression >10%/>15% with 5 ms floor. No source modification, dependency change, cache, worker-default tuning or benchmark-only substitution was made.

Primary commands (`PATH` selects Node 20; `uv --directory backend` selects Python 3.12.11), exact argument arrays/exits in `commands-matrix.json`, `commands-supplement.json`, `commands-followup.json` and `latency-confirmation/commands-supplement.json`:

```sh
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend python /tmp/tti-final-20261023/main-performance/run-matrices.py
PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-final-20261023/main-performance/followup-imports.py
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend python /tmp/tti-final-20261023/main-performance/run-supplements.py
PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-final-20261023/main-performance/latency-confirmation/run.py
PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-final-20261023/main-performance/publish.py
```

All product measurement/build/graph/semantic children exit **0**; focused tests **232 passed**. Own exact-main tiny `make bench` ran once: **11 passed**, exit **0**. No parent broad gate was repeated. Publication succeeds with closed schemas, raw recomputation, round trip and eight privacy/sampling rejection cases. Source remains clean at exact main; three prior numeric artifacts retain their original hashes.

Retained non-product failures: final cleanup observer first exited **1** assuming its stored assertion PID still existed; corrected observation records `already_absent`, not continuous protection. Initial report parse exited **1** on a missing token space; the next validation exited **1** because the reused old success-only schema rejected actual nonzero failed-request counts. The report-only count type now preserves those failures, and the zero-error acceptance check stays **false**. Original scripts/receipts are retained, no timing rerun or budget relaxation resulted. Some file-preparation/environment/log utilities used system Python; all product timings and final validation used Python 3.12.11. Parent's separate main quality-wrapper failure remains archived under `main-acceptance/wrapper-failure.json`; full/build passed before that path-construction error, with no code change or duplicate full rerun claimed here.

Private raw sources: `reference-matrix.json`, `main-matrix.json`, `*-matrix-trials.json`, `phase-trials.json`, `*-contention.stdout.log`, `*-repeated-imports.json`, `retirement-inventory.json`, `*-browser.json`, and `latency-confirmation/` reports/trials. Generated XML/DBs, clinical-valued synthetic oracles/envelopes, source maps and raw child logs remain private. Artifact/method hashes in the closed JSON support independent verification. All normal/follow-up statistics are separate; no incompatible source/power phase or sample count is pooled.

Limits: one fresh main/reference matrix pair; n=3 import/phase peaks have p95=max; bounded seven-import confirmations and two browser pairs are not confidence intervals. Short subprocess waits and frame scheduling are coarse, normal desktop load/thermal/frequency state is uncontrolled, and failed-request reasons are unavailable. The persistent cached-chat result is the measured blocker, not a claimed root cause. No hosted inference, physical phone, physical power loss, private-catalog adversary or full personal Apple Health export was qualified. Parent-supplied main CI run 39851476974/all ten jobs, 1,390 backend/224 frontend full gates, actual platform/browser/fault receipts and audit dispositions remain separate evidence; no CI/issue mutation or polling occurred here. No source commit or PR was created. Parent obtains fresh independent outcome acceptance before closure.
