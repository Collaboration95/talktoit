# Roadmap delivery evidence

This index tracks the 22 October 2026 delivery run from `main` at `49510a7`.
The integration branch is `codex/dev-roadmap-20261022`. All GitHub access uses
authenticated `gh`; all verification data is synthetic and remains local.

## Delivery decisions

The user's current instructions supersede the original execution charter's
one-leaf-per-PR and per-PR review requirements. Related leaves share cohesive
PRs targeting the integration branch. Independent review runs against the final
integrated result. At most five Sol 6.1 children may run concurrently, with fast
service enabled. Children may not launch other agents. Luna design/research
tasks do not consume that limit. Each writer has an isolated worktree.

Tests precede behavior changes. Focused tests run without coverage during
iteration; complete surface checks and coverage gates run before integration.
Concurrent pytest runs cap automatic workers at two. Performance measurements
must run without competing delivery workloads before they establish a baseline
or support an improvement claim. Existing Ruff/pre-commit tooling remains the
canonical fast verification path.

## Batches

| Batch | Issues | Boundary | Evidence |
| --- | --- | --- | --- |
| Owned shards and CLI identity | #153, #154 | Coordinator and CLI cache association | PR #202 merged at `d81464e`; nine CI checks passed |
| Durable activation | #156, #157, #158 | Selected lifecycle protocol and crash recovery | PR #205: original CI passed; integration update pending |
| Generation identity and retirement | #160, #161, #162, #163 | Leased generation, deletion, owned cleanup | Waiting for durable activation |
| Supported maintenance | #140, #141, #142, #144, #145, #146, #147 | Toolchain, audit fixes, macOS smoke, historical reconciliation | PR #204 merged at `475e673`; ten CI checks passed |
| Dashboard scope | #167, #168 | Explicit dataset periods and recoverable empty filters | PR #203 merged at `82c42bf`; ten CI checks passed |
| Daily-use guidance | #170, #171, #173, #174, #175, #197 | Onboarding, import jobs, truthful chat/provider/route states | PR #206 merged at `c461341`; ten PR CI checks passed |
| Analytics decisions | #192, #194 | Sleep and metric comparison contracts | PR #201 merged at `4d766aa`; nine CI checks passed |
| Analytics implementation | #193, #195 | Shared measured queries, tools and templates | Waiting for identity and chat contracts |
| Measured performance | #179, #180, #181, #183, #184, #186, #187, #188 | Reproducible baseline and selected candidates | Supported baseline integrated; harness in progress; quiet measurements pending |

The performance batch comprises #179, #180, #181, #183, #184, #186, #187 and
#188. Candidate issues permit a measurement-based no-change disposition; such a
disposition must include reproducible evidence and must not claim a speedup.

## Final acceptance

The maintenance (#148), data safety (#164), daily-use (#176), performance
(#189), analytics (#199), and whole-roadmap (#150) gates remain open until their
specific acceptance evidence exists. An open PR, green targeted test, or design
note does not establish full roadmap completion. Historical issues remain
unchanged while #142 classifies their current evidence. Optional companion/ZIP
discovery (#198) does not block the required roadmap and does not advertise a
supported feature.

## Integrated checkpoint

The integration branch passed all ten CI checks at `82c42bf`, including the macOS
synthetic lifecycle smoke. Daily-use merge `c461341` has not yet received its
integrated CI receipt at this checkpoint. Its own PR passed all ten checks.
PR #200 remains a draft; final independent review and outcome gates are pending.

Detailed reproducible evidence lives in:

- `maintenance-baseline-2026-10.md`, `dependency-remediation.md`, and
  `dependency-disposition-2026-10.md`: Node 20.20.2/Python 3.12.11, locked installs,
  full checks, official synthetic V2 counts/relationships, and audit inventory.
- `audit-reconciliation-2026-10.md`: all 55 historical open issues classified;
  historical issues remain unchanged.
- `daily-use-acceptance.md`: tests and real-browser DOM acceptance for import,
  starters, chat, saved privacy, and routes.
- `sleep-chat.md` and `metric-comparisons.md`: accepted implementation contracts
  and the synthetic sleep-semantics oracle; feature implementation remains pending.
- PR #202: 494 backend tests; A=45.5/B=999-minute cache identity regression;
  sentinel, retry, symlink, concurrent shard and worker-parity coverage. Coverage
  was 86.85% overall, 91% ingestion, and 83% LLM.
- PR #203: 176 frontend tests on its original source, 59 focused tests, and real
  browser DOM/request evidence for periods, URL history, saved scopes and Reset.
  Its integration update passed CI under the maintained Vitest 4 toolchain.

Python and production-only Node audits passed. The full Node audit still exits 1
with seven vulnerable packages arising from two documented Tailwind 3 development
tooling advisories. Audit gates remain enabled. These dispositions and the
existing Tremor/React peer mismatch remain explicit final-review inputs; a clean
all-dependency audit is not claimed.

Browser navigation and DOM interactions work, but snapshot capture repeatedly
reported `Preview automation snapshot timed out after 15000ms.` Screenshot/visual
acceptance and the complete restart/cancel/phone-width journey remain pending.
No performance baseline or speedup is claimed while competing test work runs.

Record remaining actual head/merge SHAs, commands and exit codes, module coverage,
Ubuntu/macOS CI links, synthetic known-value and crash/race evidence, browser
acceptance, independent review, performance metadata, and limitations here as
batches land. Integrated tests establish the checkpoints above; they do not close
the whole-roadmap acceptance gate.
