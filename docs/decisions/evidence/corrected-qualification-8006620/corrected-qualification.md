# Corrected bounded #189 qualification — H800

**PASS for the authorized bounded qualification.** The single natural confirmation and all five fresh corrected browser primary metrics satisfy the unchanged rules. No browser confirmation was triggered or run. This is a measurement receipt; independent final outcome acceptance, integration and issue closure remain parent-owned. The original actual-main **REVISE** reports and every failed/outlier trial remain unchanged and separately labelled.

[Closed numeric results](corrected-qualification-results.json) contain all **44 browser trials and 44 natural trials**, including all eight discarded warmups, recomputed median/nearest-rank p95/population variance and standard deviation, min/max, request/error counts, source/method/runtime/window identities and provenance. Each head/group has **2 discarded +20 retained** observations. No outlier was removed or replaced. [JSON schema](corrected-qualification-schema.json), [validation receipt](validation.json) and [artifact manifest](artifact-manifest.json) support offline checking. Raw URLs, generation IDs, synthetic question/response content and exact private argv remain private.

## Source, method and authority

| Role | Production pin | Executed checkout | Common browser harness |
| --- | --- | --- | --- |
| Main | `a0ac51b6a24442f669608f153efe5b0c98931051`, tree `3de52384a0c216eaf597f9293e1eb9c3dda6a881` | H `8006620ec27f06dd9834b5cfdc268974c2f439fc`, tree `649fb8539ffa04e9a06913dff95263baec0d969d` | H800, both heads |
| Reference | `859f89a405499ecef024fb8dde127a5f3d7c2f77`, tree `13e56c633e8c9c55cafb2d53e68cc15d07c015c6` | Exact reference checkout | H800, both heads |

The six-file protocol digest is **`9ee6b4a46b06ca2e6b74acb0619d4e0b44cc9f7805fb05ecb217de30f7b3ef04`**. Production components/configuration/locks match the pinned source pair; component/test IDs in JSON describe the executed checkouts. H includes the previously tested frontend tests, not a production change. Source and harness identities are separate. No repository/source edit, build, commit, push, GitHub mutation or agent was performed during this window.

The R3 implementation report hash is `2be79a68291740522b5754a2a019beed3b8992ab77090ff3510032979bf48da7`. Its conditional CI requirement was discharged by the parent and bound in the supplied freeze: H800, eleven successful checks, run **39867103866**, Ubuntu job **120131931189**, 47/47 functional criteria, deliberate hard-stop −9/recovery 0, test merge `e83d09efa6463f4b6c52f877016217e494affc8e` with exact H tree. These are supplied verified authority, not a new CI query or independent outcome review here. Freeze/plan/review/CI hashes are in JSON; the frozen orders, sample counts and stop policy were loaded before results.

Natural confirmation ran **main→reference**. Browser primary ran **reference→main**. The original production helper module SHA-256 remains `5f7ae55d7469dbe055d0bc092aaba7226a747b9d42a5d74be8f512b10e77dd74`. Its natural-phase prefix is byte-verbatim; the adapter only emits results/assertions after that phase and omits the unrequested later exact-hit/controlled-barrier workloads. Prefix/selected-function/adapter hashes are retained. The original writer, profile event, fresh-question request timer, real conversation/pending-turn path, parity and terminal assertions are unchanged. This is not a no-conversation or no-writer proxy.

Both groups use the representative generated seed-137 corpus: 500,000 records, 8,192 workouts, 180 days. Public leased snapshots verify counts, known private values/relationships and source-specific immutable generations. Browser setup uses one official one-worker import/head outside product timers. Natural setup reuses the same source-specific parity-verified generated corpus with fresh isolated app state. All corpus digests agree. No importer algorithm, worker policy, lifecycle, cache, query or provider behavior was optimized.

## Fresh results

Cells are **median /p95 /population σ milliseconds**, n=20 retained/head. Variance and all raw observations, including warmups and extremes, are in JSON.

| Browser metric | Reference | Main |
| --- | --- | --- |
| Cold input +2 frames | 113.40 / 118.40 / 9.12 | 74.40 / 83.80 / 7.20 |
| First visible nonzero chart canvas +2 frames | 210.55 / 228.20 / 11.69 | 187.40 / 211.90 / 13.73 |
| Cached Chat shell +2 frames | 59.20 / 68.80 / 3.92 | 62.95 / 69.50 / 4.55 |
| Cached Dashboard canvas +2 frames | 146.20 / 148.20 / 3.48 | 131.35 / 147.70 / 25.29 |
| Volume response completion +2 frames | 193.80 / 207.20 / 19.70 | 76.55 / 88.00 / 4.78 |
| First-chart locator upper bound (diagnostic only) | 211.00 / 228.50 / 11.47 | 211.60 / 213.50 / 7.87 |

All five primary rows pass. The locator upper bound remains diagnostic and cannot trigger or replace a primary result. Cached Chat is **59.20/68.80 →62.95/69.50 ms**: median +3.75 ms/+6.33%, p95 +0.70 ms/+1.02%. The clock still starts **before** the Chat locator click, ends after the visible/enabled idle input and exactly two frames, and includes automation/actionability/frame scheduling. Settings/history completion is not substituted for shell readiness.

Within this fresh same-protocol pair, main's median cold-input cost is 39.00 ms/34.39% lower, first-chart cost 23.15 ms/11.00% lower, and volume-response cost 117.25 ms/60.50% lower. Cached Dashboard median is 14.85 ms/10.16% lower, with substantial dispersion: main min64.50/max148.10/σ25.29 ms versus reference σ3.48 ms. These are bounded current measurements, not a machine-independent promise. No causal explanation is assigned to the historical regression. First canvas and volume response plus two frames are **not animation completion**.

| Natural confirmation component | Reference | Main |
| --- | --- | --- |
| Natural conversation HTTP/ASGI | 15.63 / 16.31 / 0.42 | 17.13 / 19.21 / 1.49 |
| Independent SQLite writer | 5.18 / 5.44 / 0.28 | 0.71 / 0.84 / 0.07 |
| Actual profile preparation | 3.36 / 3.57 / 0.11 | 3.55 / 3.79 / 0.25 |

Natural main p95 is **2.90 ms/17.78% higher**. Its relative increase exceeds 15%, but the difference is below the original 5 ms floor; median difference is 1.49 ms/9.56%. Thus the primary **18.37746→33.46104 ms** tail flag is **not confirmed under the predeclared rule**. It is not deleted or retroactively passed. There was exactly one confirmation pair, with no further natural retry. Main's retained maximum22.11 ms is included.

Each natural source records 22 profile calls across all trials, 20 retained calls, two alternating distinct fresh questions, one completed real turn/request and an independent writer. Provider/network attempts are zero. Exact-cache/profile-bypass and injected-hold barrier evidence remains the separately reused original group; neither was remeasured or inferred from the normal writer timings.

## Counts, errors and fixed rules

| Browser action | Reference | Main |
| --- | ---: | ---: |
| Mount | 9 | 9 |
| Month toggle | 8 | 1 |
| Scope change | 8 | 8 |
| Chat-return panel requests | 0 | 0 |
| Dashboard remount | 9 | 9 |

Counts hold for **every trial, including warmups**. The append-only ledger spans all phases through final settlement. Every captured API row has status200 and successful browser body completion; HTTP/transport/body/parse failures, unexplained or intentional cancellations, incomplete bodies, page errors and provider/network/external requests are zero. Classification never filters an error. The current all-panel body/render barrier, including all fresh/nonzero summary canvases and legitimate empty states, is used identically on both heads. Readiness probes are explicitly denied; denied counts are retained, not remote latency fabricated as zero.

A statistic flags only when **its own difference is ≥5 ms AND its ratio exceeds its limit**: median>1.10× reference, p95>1.15× reference. A primary metric fails if either statistic flags. Useful median gain requires both ≥10% and ≥10 ms. All flags use unrounded observations. None of the five primary browser metrics triggered the frozen conditional confirmation, so zero confirmation pairs were used. Warmups were discarded only by ordinal1/2; every retained observation contributes. No timing definition, threshold, wait, source or sample count was adjusted after results.

## Conditions and cleanup

Actual runtime: Python3.12.11, Node20.20.2, DuckDB1.5.4, Playwright1.63.0, installed **Chrome155.0.8059.85**, 390×844. The actual Chrome executable path is private; binary SHA-256 is unchanged before/after. Hardware is AppleM5, 10 logical CPUs,32GiB, macOS26.6.2/Darwin25.6.0. All locks match the accepted setup. No runtime substitution or pooling with functional Chromium153 occurred.

Owned assertion window: **2026-10-22T23:00:03+00:00–2026-10-22T23:04:14+00:00**, 251.03s, covering the 75.02s formal-command span. Every checkpoint reports AC/95%, low-power modes0. Load averages start 3.03, 3.02, 3.04, end 3.29, 3.12, 3.08. System power log records zero sleep/wake/battery-power events in this window. The owned idle-sleep assertion was observed live 1211 times, maximum observation gap 0.389s, present in final pmset, then deliberately terminated (−15). This is sampled liveness, not an unobserved physical guarantee.

Normal desktop apps remained open, including Brave, ChatGPT, Docker, Outlook/Word, Safari, T3 Code, Telegram/WhatsApp, VS Code and Xcode; no unrelated process was killed. Sanitized app/process CPU/RSS snapshots are included; during-browser snapshots also include owned Chrome/Python. Start sampled WindowServer was52.3% and grouped other system/user processes70.8% of one CPU. Desktop/observer/thermal/frequency scheduling remains a limitation. The liveness observer sampled about every0.2s and wrote its private checkpoint, identically across both heads.

All four qualifying commands exited0. All owned servers, Chrome runs, natural subprocesses and the assertion are stopped; owned ports were checked clear. The quiet window was released immediately after formal work. Exact private argv/exits and capture hashes are retained. One premeasurement controller syntax check exited1 and was corrected **before any trial**; its source/error record remains archived. No failed/partial qualifying command, replacement trial or publication failure occurred.

## Explicit composition and immutable failures

| Evidence group | Provenance / disposition |
| --- | --- |
| Normal backend matrices | Original a0ac/reference AC window, unchanged original matrix/common harness; **96 raw imports/72 retained +528 raw workloads/480 retained**, not624 retained samples. Reused by exact group identity. |
| Production XML validation/scan | Original source/helpers/window and1+3 process rule; capture/activation/recovery overhead remains in the original full-import measurements. Reused; no scratch result substituted. |
| Numeric trend | Original helper transfer/parity/RSS and1+3 process/2+20 inner-query groups;125,000→26 structural result retains its old measurement labels. Reused, not rerun. |
| Writer/barrier/profile/exact | Original source/kernel/raw groups and zero exact-hit profile scans retained; controlled hold remains labelled injected mechanism, not natural p95. New natural group is separate. |
| Retirement, bounded import followups, workout confirmation | Original timers/oracles/groups and distinct1+3/1+7 rules preserved; ranked-query resolution and profile/summary-table NO-GO reopening rules unchanged. |
| Static graph/build | Retained exact input/output equality: eight files/manifest,230,763raw/71,199gzip, zero initial ECharts. No new graph/build workload or timing. |
| Old browser primary/confirmation | **Historical REVISE**, both old source/protocol pairs, unchanged failures/outliers and unknown panel error reasons. Never pooled with corrected readiness. |
| Instrumented diagnosis | **NONQUALIFYING**, parallel observation window, retained as mechanism/method evidence only. |
| Corrected browser primary | **Fresh PASS**, H800 body-render-v1, reference→main,2+20/head, five primary metrics, no triggered confirmation. |
| Natural confirmation | **Fresh PASS under original margins/floor**, exact original natural kernel, main→reference,2+20/head, primary tail not confirmed. |

Reuse is supported by unchanged complete production/config/test/lock inputs, seven common benchmark modules, all47 original raw/method bindings, corpus/oracles, original invocation/environment/denial settings, time units and timer definitions, independently verified in R3 and rechecked before this run. Production IDs and the R3 equivalence hash are in JSON. Reused sampled simultaneous process-tree RSS remains summed sampled RSS, not PSS/USS/true peak; n3 ingestion p95=max/reference-only. **New browser/natural RSS was not measured.** No unchanged matrix/phase/retirement/trend/graph or broad frontend/backend suite was rerun. This is a composed qualification, not a new make check-full.

Original main Markdown hash stays `235018f9af1f8e27818233445e892345862110339d5ac203224fa7d137d8ef24`; original1,431,881-byte JSON stays `f89c33d170d3efc994fe5821fd31b863481ebed8e5454505210383cd4a30aac1`. The old cached-chat pairs remain58.30/69.90→69.20/84.50 and59.30/70.50→67.65/85.20ms. Original retained panel failures remain primary7 and confirmation5/12/20, plus warmup2; their reasons stay unknown. All three baseline/BLOCKED-portfolio/chart-repair numeric hashes are preserved in JSON. No old source/window is relabelled current, and no source cause is claimed.

## Reproduction and validation

Actual private command receipts bind the four executions in order: natural-main0, natural-reference0, browser-primary-reference0, browser-primary-main0. Both browser commands used the committed common controller:

```sh
# In H800 with supported Node20/Python3.12; use fresh output directories.
uv run --directory backend python ../scripts/browser-acceptance/performance-run.py \
  --source "$REFERENCE_CHECKOUT" --production-head 859f89a405499ecef024fb8dde127a5f3d7c2f77 \
  --role reference --toggle-count 8 --mode qualification --method-review "$FREEZE_JSON" \
  --channel chrome --artifacts "$FRESH_REFERENCE_OUTPUT"
uv run --directory backend python ../scripts/browser-acceptance/performance-run.py \
  --production-head a0ac51b6a24442f669608f153efe5b0c98931051 \
  --role main --toggle-count 1 --mode qualification --method-review "$FREEZE_JSON" \
  --channel chrome --artifacts "$FRESH_MAIN_OUTPUT"
```

The private natural adapter uses the bound original module/prefix with fresh state and the original synthetic source-generation mapping; exact argv, source checks and kernel hashes are retained. It is not replaced by generic HTTP. These commands document this completed run, not permission to repeat it. The frozen maximum was one natural pair and at most one conditionally triggered browser confirmation.

Offline publication independently recomputed every new statistic/flag, checked exact2+20 ordinal membership, all raw ledger deliveries/zero errors, source/corpus/method identity, full raw warmups/outliers and cleanup. Closed schema/privacy round-trip passes, with **12 negative cases rejected**: unknown question/endpoint/SQL fields, altered warmup membership, missing trial, hidden warmup error, wrong sample count/method hash, falsified median, diagnostic promoted into primary flags, loosened floor and missing natural profile call. Publication exited0. Supporting method/raw capture hashes are bound without publishing private payloads.

Limits: one corrected primary browser pair and one natural confirmation, n20/head, no confidence-interval/SLA claim; fixed current setup and nonzero desktop load; fresh contexts and reset synthetic app caches with warm server/OS caches; first-canvas readiness rather than animation completion; cache shell rather than restored transcript; ASGI natural costs distinct from real TCP browser costs; no inference latency, physical phone, physical power-loss or full personal-export guarantee. Parent still owns publication/index composition, final exact-head CI reconciliation, promotion to actual main and fresh independent five-gate outcome acceptance. No issue is closed by this PASS.
