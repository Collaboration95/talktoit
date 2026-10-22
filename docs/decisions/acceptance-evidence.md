# Roadmap delivery evidence

This index tracks the 22 October 2026 delivery from `main` at `49510a7`.
The integration branch is `codex/dev-roadmap-20261022`; umbrella
[PR #200](https://github.com/Collaboration95/talktoit/pull/200) targets `main`.
All GitHub operations use authenticated `gh`. Verification uses isolated synthetic
data and denied providers. Personal exports and generated databases are excluded
from commits. The existing untracked `reports/` remains untouched.

## Delivery decisions

The user's instructions supersede the original charter's one-leaf-per-PR,
two-writer limit and per-PR independent review. Related leaves share cohesive PRs
targeting dev. Final independent review assesses the integrated result; material
findings receive regressions, corrections and a fresh review round.
At most five Sol 6.1 children run concurrently with fast service enabled;
children may not launch other agents. Writers use separate worktrees.

Meaningful regressions precede behavior changes. Focused checks support quick
iteration; full affected surfaces and unchanged coverage gates qualify each batch.
Pytest automatic workers and Vitest workers are capped at two locally. Existing
Ruff/pre-commit checks remain the commit verification path. Timed measurements
run in a separate quiet phase without competing local tests, builds or browser
journeys. Prototype selection and production acceptance evidence remain separate.

## Integrated batches

Every batch below is merged into dev. Final PR checks passed: nine for #201/#202,
ten for #203–#211 and eleven for #212. These receipts establish integration checkpoints; they do not
substitute for final review or merged-main acceptance.

| PR | Required leaves | Result | Dev merge |
| --- | --- | --- | --- |
| [#201](https://github.com/Collaboration95/talktoit/pull/201) | #192, #194 | Sleep/comparison contracts | `4d766aa` |
| [#202](https://github.com/Collaboration95/talktoit/pull/202) | #153, #154 | Owned shards; CLI cache isolation | `d81464e` |
| [#204](https://github.com/Collaboration95/talktoit/pull/204) | #140, #141, #142, #144, #145, #146, #147 | Toolchain, dependency fixes, macOS smoke, historical reconciliation | `475e673` |
| [#203](https://github.com/Collaboration95/talktoit/pull/203) | #167, #168 | Dataset periods; recoverable empty filters | `82c42bf` |
| [#206](https://github.com/Collaboration95/talktoit/pull/206) | #170, #171, #173, #174, #175, #197 | Import/onboarding, truthful chat/provider/route states | `c461341` |
| [#205](https://github.com/Collaboration95/talktoit/pull/205) | #156, #157, #158 | Durable activation and hard-exit recovery | `d2d33b9` |
| [#207](https://github.com/Collaboration95/talktoit/pull/207) | #160, #161, #162, #163 | Leased consumers, deletion and artifact/job recovery | `b9ccec6` |
| [#208](https://github.com/Collaboration95/talktoit/pull/208) | #193, #195 | Measured sleep and metric comparisons | `aef8b4b` |
| [#209](https://github.com/Collaboration95/talktoit/pull/209) | #179, #180, #181 | Baseline harness; bounded validation/mmap | `f45a1db` |
| [#210](https://github.com/Collaboration95/talktoit/pull/210) | #183, #184, #188 | Short write scopes; SQL buckets; profiling NO-GO | `4fba4c0` |
| [#211](https://github.com/Collaboration95/talktoit/pull/211) | #186, #187 | Independent volume; deferred charts | `51bc6dc` |
| [#212](https://github.com/Collaboration95/talktoit/pull/212) | #187, #176, #199, #150 | Chart repair, portable browser and phone-width Settings | `476bbd2` |

Integrated checkpoint: `476bbd25e0cceb5202f6ab591c6e1ddde50313f5`, all eleven
checks passed ([run](https://github.com/Collaboration95/talktoit/actions/runs/39817790401)).
Actual Ubuntu browser acceptance passed all 47 criteria; its test-merge tree matches
this checkpoint. Final round 1 found five P2 gaps, documented below. The correction
branch is being qualified; work stays In progress/Review until fresh independent
acceptance, actual main receipts and completion comments exist.

## Criterion-to-evidence map

| Gate | Required outcome and current evidence | Remaining qualification |
| --- | --- | --- |
| #148 maintenance | Supported Python 3.12.11/Node 20.20.2; locked installs; audit dispositions; Ubuntu suites/macOS lifecycle CI; 55 historical issues classified | Fresh audits, integrated review and main CI |
| #164 data safety | Process-death activation/deletion/retention matrices; two-dataset identity/cache tests; leases; simultaneous import/query/delete; owned-artifact recovery | Final integrated fault matrix and main/platform receipts |
| #176 daily use | Combined real-browser journey passes all 47 criteria: native upload, reconnect/cancel/SIGKILL recovery, keyboard, scoped dashboard, empty-filter Reset and desktop/390 px screenshots | Actual Ubuntu browser CI, review and main receipts |
| #189 performance | Frozen matrices; production portfolio; implementation parity; repaired charts pass quiet paired browser qualification | Final review and merged-main rerun; original chart blocker is cleared |
| #199 analytics | Shared sleep union/stages; independent HTTP/CLI/query oracles; fresh combined browser coverage/missing/zero states and provider-denied rendering pass | Review and main/platform receipts |
| #150 whole roadmap | Twelve batches integrated; architecture/issue map and reproducible setup | Corrected-source review, all five gates, main integration and handoff |

No gate is closed at this checkpoint. Optional companion/ZIP discovery #198 is
outside the required roadmap. XML upload does not include companion GPX files;
the UI explains the existing local import route. Historical issues remain
unchanged: 28 repaired, 8 residual and 19 unverified; classification does not claim
acceptance or close them.

## Current corrected candidate

Round three passed UX/analytics but reproduced three cleanup gaps: missing legacy
ownership proof could be manufactured on retry, a child file could be replaced
between validation and unlink, and artifact recursion could resolve a replacement
path. [Original reports](reviews/README.md#round-3) remain historical.

Product source `86296497b6063d8148e43a73a7d621c0ed6ba154` integrates all three
responses in [the legacy fence](legacy-deletion-authority.md) and
[shared format-2 capture protocol](ownership-claim-response.md). Original authority
is persisted before same-filesystem capture; captured objects are validated before
private disposal. Replacements, ambiguous state and original proof remain preserved.
Private claim contents are trusted. Empty metadata/completion tombstones remain;
quarantine, changed locators and ambiguous preparation require manual recovery.

The exact combined app/test trees passed `make check-full`: **1,390 backend and
224 frontend tests**, overall **89.01%**, ingestion **91.55%**, LLM **82.30%**;
all thresholds unchanged. Parent verified the same trees, production build exit 0,
real macOS browser **47/47**, actual hard stop -9 and recovery exit 0, then quiet
small `make bench` **11 passed**, exit 0. This is premerge evidence, not actual-main
qualification. Earlier production timings retain their original source identities.

The Ubuntu browser job at obsolete `5105dc5` was cancelled after its unchanged
15-minute budget: dependency setup consumed 14m22s on a slow Azure APT mirror.
The new workflow pins Ubuntu 24.04, caches the locked headless shell, avoids
unconditional APT upgrades and verifies libraries by actually launching Chromium.
All scenarios, artifact assertions and the timeout remain enabled. Updated-source
Ubuntu execution and fresh independent acceptance are pending. No gate is Done.

## Final review corrections

Independent round 1 at `476bbd2` returned maintenance/performance PASS and safety
and UX/analytics REVISE. Original reports remain in [the review index](reviews/README.md).
Two correction owners implemented all five findings in one combined batch:

- #193/#170: complete supported sleep periods or local clarification, explicit
  unsupported stage/category guidance, numeric-validity-aware starter states and
  cache v7. True zero and categorical sleep remain available. See [the receipt](review-corrections.md).
- #160–#162: shield and drain chat/profile/dashboard workers before releasing
  their connection/lease, including repeated cancellation. Durable proven retirement
  candidates prevent normal superseded rollback copies accumulating; protected,
  leased, changed and unknown data stay preserved. See [the safety receipt](safety-review-corrections.md).

Combined source `ebac37d` has backend app/test trees identical to the correction
owner's full gate: **1,106 backend /224 frontend tests**, unchanged coverage gates,
88.80% overall backend coverage, ingestion 92% and LLM 82% (rounded module output).
The parent rebuilt and reran the real macOS browser journey: **47/47 pass**, exit 0,
including actual SIGKILL/recovery. Quiet `make bench`: **11 pass**, exit 0.
That source was superseded by subsequent review corrections. Earlier production
timings retain their exact source identities; main qualification must rerun the
required performance cases after these backend changes.

## Detailed evidence

### Round-two findings and next candidate

Round two passed maintenance/performance but reproduced three remaining gaps:
leading date fragments, NREM/expanded REM wording bypassing local sleep policy,
and replacement of a retirement directory after its initial ownership check.
No real provider transport ran. [Round-two reports](reviews/README.md#round-2)
retain the observations; [sleep corrections](review-corrections-round-2.md) and
[anchored cleanup](safety-review-corrections-round-2.md) record the responses.

Historical combined product source `7d398f0` consumes a bounded complete sleep
request/date grammar, shares known category/stage aliases with projection guards,
and uses cache v8 to reject prior v7 answers. Cleanup validates persisted directory
identity after the exclusive lease and uses descriptor-relative unlinks. Empty
directories/lease metadata remain; old deletion intents without identity preserve
present files for local recovery.

The combined gate passed **1,238 backend /224 frontend tests**, overall **88.90%**,
ingestion **91.55%**, LLM **82.30%**, with thresholds unchanged. Parent-confirmed
app/test trees match that gate. Rebuilt real macOS browser journey: **47/47 pass**,
exit 0; quiet small `make bench`: **11 pass**, exit 0. Round three subsequently found the cleanup gaps recorded below. Main and all outcome gates remain open;
earlier production timings stay pinned to their original source identities.

- [Baseline](maintenance-baseline-2026-10.md), [dependency decision](dependency-remediation.md)
  and [dispositions](dependency-disposition-2026-10.md): toolchain, locks, audits,
  official synthetic counts and workflow validation.
- [Historical reconciliation](audit-reconciliation-2026-10.md): all 55 issues with
  residual/unverified acceptance items.
- [Lifecycle protocol](dataset-lifecycle.md) and [artifact ownership](import-artifact-ownership.md):
  commit point, ordered locks, leases, tombstones, cancellation and actual process
  death. Targets local POSIX filesystems; physical power loss is not simulated.
  Ambiguous artifacts are preserved rather than guessed safe to delete.
- [Daily-use acceptance](daily-use-acceptance.md): component/API regressions, native
  import, truthful starters/fallbacks and saved provider disclosures.
- [Portable browser acceptance](browser-acceptance.md): real FastAPI/Chromium,
  official XML importer, actual cancellation and SIGKILL restart, independent
  analytics oracles, 47 passing local criteria and a new Ubuntu CI job. Its
  phone-width checks first caught Settings expanding to 451 px; wrapping the
  displayed command fixed the issue without disabling assertions.
- [Handoff](roadmap-handoff.md): reproducible setup, architecture constraints,
  safe continuation, measurements and deliberately deferred scope.
- [Sleep](sleep-chat.md) and [comparison](metric-comparisons.md) contracts: measured
  semantics, interval unions and coverage. The parent's independent synthetic
  oracle verified 14.5 hours across the two sample sleep days, 90,954 steps,
  HTTP/CLI identity and three metric comparisons with zero provider calls.
- [Frozen performance baseline](performance-baseline.md) and [numeric evidence](performance-baseline-results.json):
  both sizes/seeds, workers 1/2/4, sample counts, outliers and power phases.
  Reference source: `859f89a405499ecef024fb8dde127a5f3d7c2f77`.
- [Ingestion](performance-ingestion.md), [chat/trends](performance-chat-trends.md)
  and [frontend](performance-frontend.md): tests-first implementation, unchanged
  parity/coverage gates, structural counts and candidate limits. Quiet `make bench`
  exited 0 at exact heads `bf06ff6`, `2e8e597` and `b568b31`.
- [Production portfolio](performance-portfolio.md) and [numeric evidence](performance-portfolio-results.json):
  actual reference/candidate matrices on matching AC power. Representative import
  RSS falls 13.3–28.2% with a 0.95–6.67% wall tradeoff; numeric trend median falls
  106.42 to 5.79 ms while transferring 125,000 to 26 rows. These gains do not waive
  the first-chart failure described below.
- [Chart repair qualification](performance-chart-requalification.md) and
  [raw numeric trials](performance-chart-requalification-results.json): exact
  repaired source `a91e884` versus the original reference, two discarded plus
  20 retained trials per head. First-chart median/p95 is 190.75/196.10 versus
  179.10/181.00 ms; cached navigation passes unchanged margins. Initial static
  JS/gzip is 230,763/71,199 bytes with zero ECharts sources; requests remain 9/1/8.

Profile caching (#184) was rejected: 2.61 ms prototype gain missed the predeclared
10 ms floor. Workout join summaries were rejected: worst tested helper p95
44.04 ms met the 50 ms budget. Reopening conditions are recorded. Synthetic
reference timings are not personal-export guarantees. Model inference remains
unmeasured.

## Explicit limits and next checks

Fresh audits on 23 October match the maintenance inventory: Python and
production-only Node exit 0 with no findings. Full Node audit exits 1 with seven
development packages (five high, two moderate) from two documented Tailwind 3
advisories. Audit gates remain enabled; a clean all-dependency audit is not claimed.
The existing Tremor/React peer mismatch remains documented. The separate pinned
Playwright browser-tooling audit exits 0 with no findings.

T3 preview twice failed with `Preview automation snapshot timed out after 15000ms.`
Native Chrome/standalone Playwright subsequently supplied actual desktop/390 px
screenshots and browser checks. The documented portable harness now supplies the combined candidate journey;
actual-main and current-source Ubuntu qualification remain required. Functional failed-chunk testing found Chrome
retains a failed dynamic import on retry; formatted data remains usable.

Primary frozen baseline matrices ran on battery, later supplements on AC. Those
latencies are not pooled. The completed production portfolio uses matching AC
conditions for both reference and candidate. Its actual first-visible nonzero
canvas plus two frames regressed from 179.60/196.20 to 479.20/495.90 ms median/p95
across 20 retained trials per head. That original result and its outliers remain
archived. The explicit-loading-state repair preserves deferred dependencies and
now passes quiet paired requalification against the original margins. Its source
`a91e884` includes the corrected Settings wrapping and portable browser harness.
The historical first-chart blocker is cleared. Current-source Ubuntu CI, fresh
independent verdicts and merged-main acceptance remain open.
