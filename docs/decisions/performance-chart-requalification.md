# Chart browser requalification — #187 / pre-main #189

**PASS for this browser requalification.** On exact fixed source `a91e8842caee5b319ad059dadb2c5ea996579591`, first visible nonzero canvas +2 frames measures **179.10/181.00 ms median/p95**, versus **190.75/196.10 ms** on the paired original reference. All latency margins, request counts, provider/error checks and initial graph criteria pass. The previous measured chart blocker is cleared; broader #189 acceptance still requires parent CI, independent review and merged-main receipts.

[Closed numeric evidence](performance-chart-requalification-results.json) includes **all 44 raw numeric trials**: two explicitly discarded warmups +20 retained trials/head, summaries, min/max/population σ, environments, definitions, commands/exits and report/method hashes. No health rows/values, question text, SQL, paths or generation IDs are published.

## Pinning and method

- Reference: `859f89a405499ecef024fb8dde127a5f3d7c2f77`, existing reference checkout. Fixed candidate: **`a91e8842caee5b319ad059dadb2c5ea996579591`**, including the committed chart repair and Settings wrap. This work uses a new `codex/chart-qualification` branch at that exact commit; no merge or application edit was made.
- Backend application code is byte-unchanged from `51bc6dcc4c0b57768fcfcb50bc70387707f29209`. Backend/frontend lock SHA-256 match both heads: `7876f551af3cf1869ab7f8c4ccccb500fd2074aa60e634fe1ee7fe000ddda47b` / `c21fa14151c29af2cb126af43274e83ad37c0f2537bc9e21881c33d838d93c9c`.
- Apple M5, 10 logical CPUs, 32 GiB; macOS 26.6.2/Darwin 25.6.0; Python 3.12.11, DuckDB 1.5.4, Node 20.20.2/npm 10.8.2; Chrome **155.0.8059.85**, installed Playwright **1.63.0**. Both metadata snapshots report clean worktrees.
- Sequential **reference→fixed**, same AC/95% phase, low-power off, owned idle-sleep assertion. The 118.23-second command window has zero sleep/wake events or battery-power mentions. Initial/final load averages: 2.10/2.69/2.93 and 2.81/2.89/2.97. Normal desktop apps remained open; sanitized app/CPU/RSS/process snapshots are in JSON. Owned loopback servers and assertion were stopped, and parent was told immediately that the window ended.

The final `/tmp/tti-portfolio-20261022/browser.mjs` direct-frame statements are byte-identical in the adapted driver. Only output locations and numeric trial packaging/storage differ; hashes bind both versions. Timed scenarios have fresh browser contexts, warm server/OS caches, the same generated representative seed-137 corpus, and reset synthetic caches/conversations. Public leased snapshots verify corpus counts, known private sums and orphan relationships on both heads. The existing synthetic immutable generation is reused; no full import matrix or application workaround was introduced.

Definitions remain: cold chat = navigation→visible input +2 frames; first chart = submit→first nonzero visible canvas observed per animation frame +2 frames; cached chat = tab return→visible input +2 frames; cached dashboard = tab return→observed visible canvas +2 frames; volume = toggle→response completion +2 frames. Locator upper bounds are recorded only as diagnostics. CDP is a separate **untimed** code-coverage pass; the earlier instrumented 185.2 ms diagnostic is not qualification evidence. Animation completion is unmeasured.

## Qualifying results

Cells are **median /nearest-rank p95 /population σ ms**, using every retained observation (n=20/head).

| Metric | Paired original reference | Fixed a91e884 |
| --- | --- | --- |
| Cold chat | 95.95 / 102.60 / 6.46 | 62.90 / 67.80 / 3.39 |
| First nonzero visible canvas +2 frames | 190.75 / 196.10 / 7.89 | 179.10 / 181.00 / 6.24 |
| Cached chat shell | 60.15 / 60.80 / 1.73 | 58.90 / 60.60 / 1.09 |
| Cached dashboard canvas | 149.20 / 150.40 / 3.66 | 132.45 / 149.60 / 29.30 |
| Volume completion +2 frames | 203.50 / 218.40 / 14.63 | 96.95 / 105.70 / 10.08 |

Unchanged regression rules: flag median >10% or p95 >15%, with a 5 ms absolute floor. Useful gain requires ≥10% **and** ≥10 ms. First chart is 6.1%/11.65 ms lower in this pair: it passes the required no-regression goal without a claim that it meets the useful-gain threshold. Cached navigation also passes; every outlier remains in the raw records.

The prior failed source `51bc6dc` recorded **479.20/495.90 ms** first-chart median/p95. That [BLOCKED portfolio](performance-portfolio.md) and its numeric artifact remain untouched. This is a historical separate-window comparison, not pooled data; prior raw individual trials were not recorded. The paired current reference establishes the repair's qualification. The fix owner identified React's roughly 300 ms Suspense throttle; this source contains the committed explicit-loading-state repair.

| Structural check | Reference | Fixed |
| --- | ---: | ---: |
| Initial static JS bytes | 1,381,072 | **230,763** |
| Computed gzip bytes | 456,513 | **71,199** |
| Initial ECharts /wrapper /zrender sources | 487 /5 /97 | **0 /0 /0** |
| Initially loaded JS resources at chat ready | 1 | **1** |
| Dashboard mount /toggle /scope requests | 9 /8 /8 | **9 /1 /8** |
| Cached dashboard remount requests | 9 | **9** |

Source maps match production entry code. Gzip is Python level 9, mtime=0, summed per initial static JS resource; it is an artifact calculation. The separate CDP pass confirms only that static entry is loaded before chart use: no eager chart preload. Initial unused function bytes are 1,082,062→120,365. Request counts are constant (σ=0), and the fixed toggle requests volume only. Each retained group records 80 explicitly denied readiness probes and zero provider/socket/DNS/external calls, page errors or failed panel requests. Inference latency is unmeasured; no ASGI subtraction was used to invent TCP overhead.

## Reproduction and limits

Private root: `/tmp/tti-chart-requalification-20261023/`. `reference-browser.json`/`candidate-browser.json` contain complete raw trials and summaries; `*-trials.json` incrementally archives all 22 trials/head. Metadata, static graph/bundle reports, command/environment/window logs and method copies are retained. Generated data, private questions, source maps and server configuration remain private. The immutable #179 numeric SHA stays `e9259eeb5b4b7a4702911ce75287a65e8524fe59cec30c42e3b56625209101fe`; prior portfolio JSON stays `696b6360a5cfc6ddc695599f8f1e9b74196a08ff61b3e0aeaeca37d9348f7d45`.

```sh
# Exact-source controller: candidate bench once, fresh production/map builds,
# static graphs, then paired 2+20 unchanged direct-frame scenarios.
PATH=/opt/homebrew/opt/node@20/bin:$PATH PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run --directory backend python /tmp/tti-chart-requalification-20261023/run-qualification.py
PATH=/opt/homebrew/opt/node@20/bin:$PATH uv run --directory backend python /tmp/tti-chart-requalification-20261023/publish.py
```

All measurement child commands exit **0**. Exact-head `make bench`: **11 passed**, exit 0. Production/map builds and graph checks: exit 0. Browser pair: exit 0, no setup failures; all warmups/outliers retained. Publication: exit 0, closed schema and privacy checks, recomputation of every timing/request summary from raw retained trials, exact ordinal/warmup counts, method/source/lock preservation checks, round trip and **eight negative privacy/sampling cases**. Node syntax, Python syntax and staged whitespace checks pass. No backend/frontend full suite, coverage gate or full import matrix was repeated, and no budget changed.

These are real loopback Chrome measurements in a verified 390×844 desktop-browser viewport, not physical-phone or animation-completion acceptance. Contexts are fresh; browser process/server/OS caches, scheduling, thermal state and background desktop load remain uncontrolled. One sequential pair supplies n=20/head, without confidence-interval or machine-independent SLA claims. Backend/import qualification is carried forward solely because code/locks are unchanged. Parent's 47-criterion functional journey, 995 backend/222 frontend tests and coverage receipts are separate evidence, not rerun here.

Only these two new artifacts are committed. Parent still owns cherry-picking them into the prepared combined PR, Ubuntu CI, final independent review and remaining merged-main acceptance/issue receipts. No new PR, merge, issue closure, CI polling or future-main acceptance was performed here.
