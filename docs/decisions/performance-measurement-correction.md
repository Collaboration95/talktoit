# Browser phase readiness correction — #179 / #189 / #186 / #176 / #150

**Implementation and functional verification only. #189 remains REVISE.** No production optimization, application change, new performance qualification, or gate closure is claimed. The [independent method proposal review](reviews/performance-method-r1.md) accepts the operational plan, not this implementation or its future results. Its exact source SHA-256 is `7cbab2700a4672dc72e11efe504e0bcae6b3f0d74b22df4e93f2c1bb988a1a36`; the supplied file had no private footer to remove.

The production pair stays main `a0ac51b6a24442f669608f153efe5b0c98931051` / tree `3de52384a0c216eaf597f9293e1eb9c3dda6a881`, and reference `859f89a405499ecef024fb8dde127a5f3d7c2f77` / tree `13e56c633e8c9c55cafb2d53e68cc15d07c015c6`. Current correction source is `bd1fe696a71e95772e54a2aac56a8c83b78ec4be`, built on the original tooling/test commit `c0918d0d54401d090084023ddaaa1c7e2b56c51e`. The protocol digest, computed over the six named driver/helper/service/controller files by `performance-run.py`, is **`9ee6b4a46b06ca2e6b74acb0619d4e0b44cc9f7805fb05ecb217de30f7b3ef04`**. Subsequent receipt documentation does not change those files. Production identity and harness identity are separate in every controller receipt.

## Immutable historical failure

The original [actual-main report](evidence/main-a0ac-performance-revise/main-performance.md) and [closed numeric package](evidence/main-a0ac-performance-revise/main-performance-results.json) are intentionally archived, unchanged, together under their original filenames. This preserves their relative evidence link and historical source labels. The Markdown's original synthetic temporary reproduction locations are historical commands, not portable installation requirements.

| Artifact | Original and archived SHA-256 |
| --- | --- |
| Markdown | `235018f9af1f8e27818233445e892345862110339d5ac203224fa7d137d8ef24` |
| JSON, 1,431,881 bytes | `f89c33d170d3efc994fe5821fd31b863481ebed8e5454505210383cd4a30aac1` |

The old primary cached-chat result is 58.30/69.90 → 69.20/84.50 ms median/p95; its confirmation is 59.30/70.50 → 67.65/85.20 ms. Both fail the original rules. Main failed panel trials 7 and confirmation 5/12/20, plus confirmation warmup 2, remain intact with historically unknown error reasons. The primary natural-chat p95 flag 18.37746 → 33.46104 ms also remains unresolved. Frozen baseline, BLOCKED portfolio and chart-repair numeric artifacts are untouched. Diagnostics do not absolve any failure or establish a production cause.

`performance-history.mjs` verifies both immutable archive hashes, source/verdict/budgets, privacy markers, all browser statistics and retained failure totals. The unchanged closed-package hash binds the original validated schema; this is not a replacement serialization.

## R2-F1 response — pending independent R3 acceptance

The [pinned implementation review R2](reviews/performance-method-r2-implementation.md) returned **REVISE** for candidate `5e9360c1dddfbcb6e0343575c4d42a1befc075c3` and digest `be3422831342aba217c8d03b4c6f50e8310304cecd553e275ba1142cc2d4b723`. That old digest is not approved for qualification. The report is archived unchanged: original and archived SHA-256 `6da80ea0960c903210dc5cc00c521f84beb7e5be0769b1a65e0758e8bc7259f2`; no private citation footer was present. Local correction verification below does not supply R3 acceptance or resolve historical #189.

R2-F1 was an observed harness false positive: nonempty Activity Rings took a canvas-existence-only branch. The smallest correction marks nonempty summary as a chart and removes that weaker branch. It now uses the existing shared predicate: **every relevant canvas** must be absent from the previous-phase WeakSet and have positive intrinsic and layout dimensions. Valid empty summary still requires its expected No data state and no canvas. All other panel rules, error ledger, primary timer code, margins and production remain unchanged.

Before editing the helper, the original reviewer Chrome probe was run unchanged against byte-identical pinned 5e helper copies. It exited **1**, reporting current_nonzero_pass=true, zero_size_accepted=true and old_canvas_accepted=true. Its exact command, log, script/helper hashes and exit are retained in `method-correction-r2-f1/red-receipt.json` and `reviewer-original-red.log` under the synthetic delivery directory. The green copy changes **only the helper import path** to this checkout; the same assertions now exit **0**, rejecting both invalid states. The original probe/report remain untouched.

Eight durable Node controls exercise the actual helper callback and the same pending settlement operation: absent canvas, zero intrinsic size, zero layout size, previous canvas, mixed fresh/zero and mixed fresh/previous sets remain pending **after body completion**, then two fresh nonzero canvases complete it. Fresh and valid-empty controls pass. On the old helper these controls produced five assertion failures and three passes (exit **1**); after the correction all eight pass (exit **0**). The extended real-browser self-test also failed before the patch on zero_intrinsic, then passed all absent/zero/previous/mixed controls after it. Its short negative-state deadlines assert pending fixture states; they are not sleeps, measurement samples or qualification-driver wait adjustments. Existing tests are retained; the extended CI-wired Node suite now has **24** passing tests.

Both-source functional receipts bind this new code commit and the new digest above. Each uses one generated small-corpus scenario, zero warmups, official import/parity verification, provider/transport denial and a trial-long zero-error ledger. No formal metrics or new matrix, frontend 227-test suite, backend 439-second suite or build was run for this render-helper-only patch. The unchanged input/output mapping below is rechecked; retained prior gates stay labelled with their original execution source.

**Do not freeze or run qualification until fresh independent R3 acceptance and the parent's explicit sole quiet-window instruction.** Parent owns PR214 integration/CI and later outcome acceptance. No new PR, comment, watcher, merge, closure or child agent is authorized by this response.

## Corrected protocol: body-render-v1

Observation is armed **before** each action. `RequestLedger` binds a request at issue time to a monotonically increasing mount/phase epoch, its exact endpoint and complete date/type/source/granularity query signature. A later response cannot acquire the new phase's identity. Its append-only event stream records issuing and event-time phases separately, HTTP status, transport reason, response-finished error, browser body completion and delivery state. Raw URLs and errors stay private.

`settlePhase` requires the exact successful endpoint multiset, response-finished plus browser `requestfinished`, no pending/failed relevant panel from another epoch, and corresponding rendered readiness. It rechecks the count/delivery contract after rendering. Wrong scopes, cursors, duplicates, unknown dashboard endpoints, missing bodies, HTTP failures, transport failures, invalid JSON and barrier/render deadlines fail. Document `networkidle` supplies none of these predicates.

`waitForRenderedPanels` observes every affected section, loading/error/chart states, selected month and current scope. It checks response-derived workout row count, expected empty states, capability labels, sleep-stage message/labels, and current nonzero canvas dimensions where chart data exists. Old canvas identities cannot satisfy the next phase; references are weak. Empty panels are legitimate. This observes current component application and canvas readiness, **not animation completion**, pixel fidelity or a new health-value parity oracle. The controller's official import/leased-snapshot oracle and existing API/CLI correctness tests supply data parity separately. No production markers, eager imports, hover/scroll/actionability priming or source-specific sleeps are added.

Counts remain mount **9/9**, toggle **8/1**, scope **8/8**, remount **9/9** (reference/main). Status belongs to mount/remount. Toggle and scope settle outside their unchanged primary timers. The cached-chat primary remains browser `performance.now()` **before locator.click**, then visible/enabled idle input and **exactly two nested animation frames**. It does not wait for Settings, conversation-list completion or transcript restoration. Click/input-observer/action-return timestamps are supplementary. No CPU/CDP/React profiling is enabled in this driver; such diagnostics remain separate and nonqualifying.

The trial ledger is never reset between phases, including Chat return and remount. A normal successful report rejects every HTTP/transport/body/parse failure, intentional cancellation and unresolved body, including warmups. Cancellation classification requires explicit observed action and correlated aborted signal; supersession also requires a later distinct volume request. Classification never subtracts from the raw aggregate or permits a normal PASS. Independent pending-cancellation cases exercise positive abort assertions and rejection of mixed unrelated HTTP/network errors. A signal aborted after successful delivery is not itself a failed request.

On failure the driver retains its partial raw ledger/events and completed trials, writes an incomplete public failure receipt when a ledger exists, and exits nonzero. It does not replace an attempt, omit a warmup/outlier, or publish a complete group from fewer than 20 retained scenarios. Public summaries have closed keys, allowlisted endpoint/phase labels and numeric metrics/counts; raw exceptions, URLs, generation IDs, questions and clinical-valued synthetic responses remain private.

## Tests and execution evidence

The real-browser `--historical-wait` switch executes the actual old `page.waitForLoadState('networkidle')` statement. With reached document idle and eight deferred panel bodies, it fails an assertion, **exit 1**. The corrected helper passes the same fixture and the body-delivered/render-still-old control. This is a behavior red, not a missing import. Unit controls cover late old-phase completion/event phase, wrong date/type/source/cursor, exact counts, HTTP 500, actual synthetic transport timeout/network error, supersession/unmount, mixed errors, parse failure, closed publication and warmup/statistic recomputation.

The App tests use the real App and controlled unresolved panel promises, retain real AbortSignals, navigate to enabled Chat before releasing them, and release late successes **and failures** without overwriting Chat. Separate tests distinguish pending Settings capabilities and selected conversation question/answer arrival from shell visibility. Existing pending-volume/stale-selection assertions remain unchanged.

| Executed check | Result / exit |
| --- | --- |
| Focused App/navigation/dashboard tests | Retained c091 source: 48 passed / 0; unchanged and not repeated for R2-F1 |
| New deterministic Node tests | 24 passed / 0, including eight R2-F1 summary controls |
| Existing and extended browser harness self-tests | 0 |
| Full frontend coverage, maxWorkers=2 | Retained c091 source: 227 passed / 0; statements 89.43%, branches 80.59%, functions 91.36%, lines 92.11% |
| `make check` | 0 |
| Production build (`make build` recipe plus Vite `--manifest`) | Retained c091 source: 0; unchanged inputs and output hashes rechecked |
| Script syntax/format; pre-commit hooks | 0 for current changes; prior Python/Ruff result retained, Python unchanged |
| Corrected helper on both pinned production sources, common committed H | One functional scenario/head, zero discarded; 0/0; no latency summaries published |
| Existing portable journey at c091, retained unchanged production | All 47 criteria true; journey/recovery 0/0; deliberate hard-stop −9; cleanup passed; not repeated for R2-F1 |
| Archive/privacy/hash/statistic checks | Current preservation/privacy checks 0; prior c091 offline verification of 724 summaries, 26 matrix/query cells and 47 bound files retained |

Pinned functional runs use the same protocol digest on both heads. Main records 9/1/8/9 and reference 9/8/8/9, with zero HTTP/transport/body/parse/page/provider/egress failures and no unresolved bodies. The existing portable journey used its installed Chromium functional runtime; it is separate from future Chrome qualification. Current functional servers are stopped and their generated artifacts retained privately; the prior portable journey completed temporary-storage cleanup.

Setup failures are retained, not qualifying observations: the first new functional attempt failed before navigation because a URL object produced a double-slash reset path (405). A behavioral red and canonical loopback-root helper fixed it; final pinned runs passed. A copied offline verifier initially used uv's backend cwd and failed to locate repository docs; only its explicit repository path was corrected. Pre-commit initially reformatted two new Python files and rejected that attempt; the reformatted source then passed hooks. No product defect, budget change, disabled assertion, or backend-suite workaround followed.

Private logs/command receipts are retained under the named synthetic `method-correction` delivery directory. The controller refuses an existing output directory and retains exact private argv/exits, official importer output, raw browser ledgers and public numeric report. No generated DB, XML, coverage/build output or private capture is committed.

## Group provenance and bounded next run

[Source-equivalence evidence](performance-method-equivalence.json) records the permitted diff, complete unchanged production/build inputs and locks, seven common benchmark modules, original adapter digests and rebuilt output hashes. Backend app is `f75d9a0948217621e380a655fbe0560f3dcb23f3`, backend tests `5bfcff185625429808f0e8db68b9d296f6170c6d`, frontend production source `9812124868edcd97694b01c31d8fae58d8a32dcb`. Frontend tests changed and were retested. Browser-tool lock stays `4b63d0083815166106973b47948eb925887d419fc91e3bb76372c610b9feadcb`; backend/frontend locks stay the original values in that artifact.

Every rebuilt production JS/CSS/HTML file matches the retained parent actual-main build byte-for-byte; the manifest matches the retained mapped build. Initial closure remains **230,763 raw / 71,199 Python level-9 gzip bytes**, one static JS chunk, zero initial ECharts/wrapper/zrender sources. This is structural verification, not a new timing. The current code/digest remains pending R3. The final gate reviewer must independently accept the mapping to the final merged head; any changed input invalidates reuse for its affected group.

| Group | Measured production / protocol | Retained outcome and next evidence |
| --- | --- | --- |
| Normal backend matrices | a0ac / 859, original matrix + seven-module common harness; original AC window | Eligible reuse: 624 raw observations, 96 imports/528 workloads, **not 624 retained**. Imports 1+3, workloads 2+20; original parity, wall/RSS and query results remain source/window-labelled. |
| Validation/scan, numeric trend | Same pair/window; original production helpers | Eligible reuse: 1+3 process observations; trend 2+20 inner queries, original transfer/parity/RSS. n3 p95=max, sampled simultaneous summed RSS limitations stay. |
| Writer/barrier/profile/exact | Same pair/window; original contention kernel | Eligible unchanged groups retain original outcomes. Natural chat is the explicit exception below. |
| Repeated import/retirement and bounded import followups | Same pair; original adapters/counts | Eligible reuse of distinct original groups; no pooling of ordinary 1+3 and bounded 1+7 followups. |
| Workout query confirmation / profile and summary-table NO-GO | Same pair; original exact helpers | Existing bounded query resolution and measured NO-GO stay; no extra query confirmation solely for tooling/tests. Reopening thresholds stay. |
| Original browser primary + confirmation | Same pair, old document-idle protocol | **Historical REVISE**, preserved; never pooled with body-render-v1. |
| Corrected complete browser | Same production pair, frozen committed body-render-v1 H | **Pending quiet run:** 2 discarded +20 retained/head; one primary pair, at most one predeclared counterbalanced confirmation for flagged latency groups. Persistent failure stops REVISE. |
| Natural conversation chat | Same production pair, unchanged original kernel | **Pending exactly one counterbalanced main→reference confirmation**, 2+20/head, two alternating fresh questions, real pending-turn conversation + independent writer; preserve profile/envelope/terminal/denial checks. No generic HTTP/no-writer substitute. |
| Changed frontend / functional browser / hosted CI | H and actual final merged head | Local checks above are new executions. Final exact-head hosted jobs/platform artifacts and independent outcome acceptance remain pending. Old a0ac CI is not renamed H CI. |

Reuse additionally requires the original raw/method files, invocation/environment/denial settings, corpus/oracles, units and timer definitions to remain bound to their recorded hashes. Offline verification checked those 47 bindings without importing product code. Full source/config equality supplies the remaining code boundary. No local 439-second backend run or unchanged full matrix was repeated. This is an explicitly **composed** receipt, not a newly executed `make check-full`; required hosted backend/coverage/fault jobs remain enabled.

Unchanged rules: regression if difference **≥5 ms** and main median **>1.10×** reference, or p95 **>1.15×** reference. Useful gain requires both ≥10% and ≥10 ms. No post-hoc slack, pooling power phases, excluded outliers or repeat-until-PASS policy is permitted. The natural primary tail flag stays separate: its single confirmation may be reported “not confirmed” only if that matched confirmation passes the original rules; persistence stops REVISE.

Future quiet browser setup must reconcile actual Chrome 155.0.8059.85, Playwright 1.63.0, Python 3.12.11, Node 20.20.2, DuckDB 1.5.4, 390×844, generated representative seed 137 corpus, fresh contexts/cache resets/leased generations, matching quiet AC/awake/load conditions and both source locks. The controller generates one parity-verified corpus/head; it does not repeat the import matrix. Existing backend groups keep their old window. No inference, physical phone, animation completion, physical power loss or full personal-export guarantee is added.

## Reusable commands

From the repository root with Node 20 on PATH:

```sh
npm --prefix scripts/browser-acceptance ci --ignore-scripts
npm --prefix scripts/browser-acceptance run self-test
node --test scripts/browser-acceptance/performance-*.test.mjs
# Expected failure (exit 1), mutation-sensitivity evidence only:
node scripts/browser-acceptance/performance-self-test.mjs --historical-wait

# One untimed functional scenario; build production frontend first.
uv run --directory backend python ../scripts/browser-acceptance/performance-run.py \
  --production-head a0ac51b6a24442f669608f153efe5b0c98931051 \
  --role main --toggle-count 1 --channel chrome --artifacts /tmp/tti-method-main-new
uv run --directory backend python ../scripts/browser-acceptance/performance-run.py \
  --source /tmp/tti-portfolio-reference-20261022 \
  --production-head 859f89a405499ecef024fb8dde127a5f3d7c2f77 \
  --role reference --toggle-count 8 --channel chrome --artifacts /tmp/tti-method-reference-new
```

`TTI_BROWSER_CHANNEL=chrome` selects Chrome for self-tests when desired; default Chromium is portable functional tooling. The controller's default is functional, one scenario and no published timings. **Do not run qualification now.** After the parent freezes H/protocol and explicitly releases the sole quiet window, use the same commands with `--mode qualification --method-review REVIEW.json` and fresh directories. That supplied receipt must contain `{"status":"PASS","protocol":"body-render-v1"}` and be tied by the parent's index to this method adjudication and pinned implementation. Fixed 2+20 counts cannot be lowered in qualification mode. Source/build/runtime/environment and final merged-head acceptance still require independent verification; the receipt flag is not acceptance authority.

The natural confirmation uses the preserved original contention helper (`production_helpers` digest in the equivalence artifact), with a fresh output/app-state directory and the same parity-verified source corpus. Any wrapper must preserve that kernel and source-specific generation mapping; it is a separate quiet followup, not implemented by replacing it with this browser driver.

No new PR, GitHub comment/status mutation, CI watcher, merge, issue closure, or child agent was created. The parent owns existing PR214; this branch supplies its fast-forward correction. Parent owns the batched PR description/base, integration, required CI, quiet measurements, final index and fresh independent gate acceptance.
