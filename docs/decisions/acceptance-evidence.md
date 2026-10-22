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
targeting dev. One final independent review assesses the integrated result.
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
ten for #203–#211. These receipts establish integration checkpoints; they do not
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

Combined candidate: `51bc6dcc4c0b57768fcfcb50bc70387707f29209`. All ten integrated CI checks
passed, including macOS lifecycle smoke and Ubuntu suites/build ([run](https://github.com/Collaboration95/talktoit/actions/runs/39803509563)). All 36 required task/spike leaves remain in Review
until final independent review, merged-main receipts and completion comments exist.

## Criterion-to-evidence map

| Gate | Required outcome and current evidence | Remaining qualification |
| --- | --- | --- |
| #148 maintenance | Supported Python 3.12.11/Node 20.20.2; locked installs; audit dispositions; Ubuntu suites/macOS lifecycle CI; 55 historical issues classified | Fresh audits, integrated review and main CI |
| #164 data safety | Process-death activation/deletion/retention matrices; two-dataset identity/cache tests; leases; simultaneous import/query/delete; owned-artifact recovery | Final integrated fault matrix and main/platform receipts |
| #176 daily use | Combined real-browser journey passes all 47 criteria: native upload, reconnect/cancel/SIGKILL recovery, keyboard, scoped dashboard, empty-filter Reset and desktop/390 px screenshots | Actual Ubuntu browser CI, review and main receipts |
| #189 performance | Frozen matrices; production portfolio; implementation parity; quiet branch benchmark gates | BLOCKED on #187 first-chart regression, then quiet repair qualification, review and main rerun |
| #199 analytics | Shared sleep union/stages; independent HTTP/CLI/query oracles; fresh combined browser coverage/missing/zero states and provider-denied rendering pass | Review and main/platform receipts |
| #150 whole roadmap | Eleven cohesive batches integrated; architecture/issue map and reproducible setup | All five gates, final checks/build, independent review, main integration and handoff |

No gate is closed at this checkpoint. Optional companion/ZIP discovery #198 is
outside the required roadmap. XML upload does not include companion GPX files;
the UI explains the existing local import route. Historical issues remain
unchanged: 28 repaired, 8 residual and 19 unverified; classification does not claim
acceptance or close them.

## Detailed evidence

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
screenshots and browser checks. These do not yet establish the complete final
journey on the combined candidate. Functional failed-chunk testing found Chrome
retains a failed dynamic import on retry; formatted data remains usable.

Primary frozen baseline matrices ran on battery, later supplements on AC. Those
latencies are not pooled. The completed production portfolio uses matching AC
conditions for both reference and candidate. Its actual first-visible nonzero
canvas plus two frames regressed from 179.60/196.20 to 479.20/495.90 ms median/p95
across 20 retained trials per head. #187 is back In progress, and #189/main
acceptance remain blocked. The original result and outliers remain archived;
repair must preserve deferred dependencies and qualify against the original
margins. Final checks, independent verdicts and merged-main acceptance remain open.
