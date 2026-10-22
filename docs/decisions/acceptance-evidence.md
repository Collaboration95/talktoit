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
| Owned shards and CLI identity | #153, #154 | Coordinator and CLI cache association | Pending implementation |
| Durable activation | #156, #157, #158 | Selected lifecycle protocol and crash recovery | Pending design |
| Generation identity and retirement | #160, #161, #162, #163 | Leased generation, deletion, owned cleanup | Waiting for durable activation |
| Supported maintenance | #140, #141, #142, #144, #145, #146, #147 | Toolchain, audit fixes, macOS smoke, historical reconciliation | Pending implementation |
| Dashboard scope | #167, #168 | Explicit dataset periods and recoverable empty filters | Pending implementation |
| Daily-use guidance | #170, #171, #173, #174, #175, #197 | Onboarding, import jobs, truthful chat/provider/route states | Pending implementation |
| Analytics decisions | #192, #194 | Sleep and metric comparison contracts | Pending design |
| Analytics implementation | #193, #195 | Shared measured queries, tools and templates | Waiting for identity and chat contracts |
| Measured performance | #179–#188, excluding unrelated issue numbers | Reproducible baseline and selected candidates | Waiting for supported baseline |

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

Record actual head/merge SHAs, commands and exit codes, module coverage,
Ubuntu/macOS CI links, synthetic known-value and crash/race evidence, browser
acceptance, independent review, performance metadata, and limitations here as
batches land. No acceptance has been asserted by this initial index.
