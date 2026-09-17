# Stacked PR Review

Review date: 2026-09-13
Repository: `Collaboration95/talktoit`
Review mode: independent review of the locally mirrored stack; no implementation,
commits, merges, or GitHub comments were made.

## Decision

**Do not merge the stack.** The base audit-remediation branch is **BLOCKED** and
every reviewed stack PR is **REVISE**. The stack addresses the local issue range
`#58`–`#121` (64 issues), but that claim cannot yet be treated as remotely
verified closure evidence.

The highest-risk outstanding defects are:

- Chat and import cancellation can leave inconsistent state or block the event
  loop (`audit-remediation`, `w5`, and `w6`).
- Ranked-workout one-sided date filters are ignored, and unit handling has
  cross-query inconsistencies (`w3`).
- Fallback answers can still be stored in cache, while invalid metric aliases
  can become measured trend data (`w4`).
- LiteRT PID ownership is unsafe and provider lifecycle/cache state is racy
  (`w7`).
- Conversation changes can be overwritten by late requests, and safe backend
  error messages are hidden from the user (`w8` and `w9`).

## Review scope and evidence limits

Each reviewer read `AGENTS.md`, engineering/work-item/audit material relevant to
their branch, reviewed its complete incremental diff, and ran focused checks.
The local refs show a linear `w1`–`w9` stack from `main`; `audit-remediation` is
a separate branch and is not an ancestor of `w1`.

No GitHub reauthentication was performed. `gh` connectivity/authentication was
inconsistent: reviewers confirmed PR metadata and passing CI for PRs #123, #124,
#128, #129, and #130, while other calls could not reach the API with the existing
invalid token. Before merge, recheck every PR's base, issue links, checks, and
comments in GitHub.

## Per-PR verdicts

| Branch / PR | Issue coverage | Verdict | Required re-review gate |
| --- | --- | --- | --- |
| `audit-remediation` | #58–#121 | **BLOCKED** | Offload diagnostics writes; make import cancellation loop-safe and process-group-safe; replace direct-orchestrator concurrency test with concurrent `/api/chat` coverage; verify remote contract. |
| `w1-ingest-correctness` / [#123](https://github.com/Collaboration95/talktoit/pull/123) | #58–#60, #115–#118 | **REVISE** | Add child-table and reordered-attribute V2 assertions across workers; assert resolved worker/fallback-warning CLI behavior. |
| `w2-ingest-robustness` / [#124](https://github.com/Collaboration95/talktoit/pull/124) | #61–#66, #88 | **REVISE** | Make child parsing attribute-order independent; wire real export roots for routes; make staging/activation cleanup fail-safe; fail closed on unexpected lock errors. |
| `w3-query-correctness` | #67–#72, #119 | **REVISE** | Respect independent `start`/`end` workout filters; choose one null/unknown-unit policy; correct `cal` conversion; preserve unavailable instead of zero; reuse duration conversion in dashboard APIs. |
| `w4-chat-cache-state` | #73–#75, #80, #89, #93, #96 | **REVISE** | Prevent fallback-envelope writes; restrict trend metrics to supported numeric definitions; restore shared activity-type display formatting. |
| `w5-async-event-loop` | #76–#79, #81, #82, #121 | **REVISE** | Publish/terminate pending turns safely during cancellable prephase; offload diagnostics error writes; unify sleep source policy; atomically coordinate health-data deletion/deactivation. |
| `w6-dashboard-infra` / [#128](https://github.com/Collaboration95/talktoit/pull/128) | #83–#87, #89, #111–#113 | **REVISE** | Synchronize import cancellation and kill process groups; add dashboard-cache single-flight; protect in-use DB connections; return JSON for exact `/api`; fix runtime version metadata source. |
| `w7-planner-provider` / [#129](https://github.com/Collaboration95/talktoit/pull/129) | #90–#92, #94, #95 | **REVISE** | Verify PID identity before signalling; remove body-weight follow-up false positive; synchronize circuit/client cache state; reap killed LiteRT process. |
| `w8-frontend-requests` / [#130](https://github.com/Collaboration95/talktoit/pull/130) | #99–#104, #106 | **REVISE** | Invalidate selection generation on all conversation transitions; display parsed safe API errors; surface create/list failures in the turn lifecycle. |
| `w9-frontend-polish` | #97, #98, #105, #107–#110, #114 | **REVISE** | Fix inherited conversation-transition and error-message defects; validate nested fallback template rows before rendering. |

## Findings by review

### `audit-remediation` — BLOCKED

- **P1:** Chat diagnostics still flush synchronously on the request event loop.
- **P1:** Import cancellation invokes task cancellation off-loop and may free a
  slot before its process has stopped.
- **P1:** The concurrency test bypasses `/api/chat`, so it does not prove shared
  HTTP/app-state behavior.
- **P2:** Dashboard panels create per-panel diagnostics repositories; work-item
  links point to untracked files.

Focused evidence: backend 355 passing tests (83.16% coverage), 147 frontend
tests, lint/type checks, and version check passed locally. Remote issue/PR
contract evidence was unavailable.

### `w1-ingest-correctness` — REVISE

- **P2:** Added tests cover root workouts but not routes, events, statistics,
  metadata, or child-table worker invariance.
- **P2:** Environment-only CLI tests do not assert resolved worker values or
  invalid-worker fallback warnings.

Focused ingestion/worker/CLI tests passed (15 targeted, 102 changed integration
tests); the reviewer reported PR #123 checks passing.

### `w2-ingest-robustness` — REVISE

- **P2:** Fixed-order child-element regexes silently drop valid reordered
  events, routes, metadata, and HRV beats.
- **P2:** `TTI_EXPORT_PATH` is not populated by normal import paths, so valid
  workout route files are refused.
- **P2:** Activation failures can orphan staged databases or leave manifest/data
  mismatch; unexpected `flock` errors proceed unlocked.

Focused ingestion/dashboard checks (23) and a 344-test backend run passed; the
reviewer verified PR #124's immediate base and reported passing CI.

### `w3-query-correctness` — REVISE

- **P1:** `get_top_workouts` discards a supplied `start` or `end` unless both
  are supplied.
- **P1:** Null duration units are interpreted differently across aggregation
  paths.
- **P2:** Dashboard duration rendering misses supported hour/second variants;
  literal `cal` is treated as `kcal`; unknown values become misleading zeroes.

Query and dashboard integration checks passed (22 and 19 respectively), but the
reviewer could not obtain remote PR/CI metadata.

### `w4-chat-cache-state` — REVISE

- **P1:** Fallback envelopes remain cache-write eligible even though reads
  reject them.
- **P1:** Metric-trend validation admits unsupported/non-numeric aliases and
  can mislabel distance values.
- **P2:** Raw activity identifiers regress into ranked/comparison UI labels.

The exact-branch backend suite passed (349 tests, 84.73% coverage). The `w3`
one-sided date-bound defect remains reproducible through this layer.

### `w5-async-event-loop` — REVISE

- **P1:** Cancelling during the off-thread chat prephase can leave a committed
  pending turn and causes synchronous diagnostics I/O on the event loop.
- **P2:** Sleep source filtering is duplicated; failed health deletion is not
  normalized/atomic; async regression coverage is incomplete.

Targeted checks (33) and a 351-test backend run passed. Remote PR/CI evidence
was unavailable.

### `w6-dashboard-infra` — REVISE

- **P2:** Import cancellation/process timeout races can leave uploads or child
  processes alive.
- **P2:** Dashboard cold misses do not coalesce, in-use DuckDB connections can
  be closed, and exact `/api` is served as SPA HTML.
- **P2:** The metadata lookup uses distribution `tti`, while the package is
  `tti-backend`; the version fallback masks this mismatch.

Focused tests (29), static checks, and reported PR #128 CI passed; direct edge
reproductions exposed the defects.

### `w7-planner-provider` — REVISE

- **P1:** PID ownership uses a command substring and can signal or block on an
  unrelated/recycled process.
- **P2:** Compatibility follow-up matching reintroduces a body-weight false
  positive; circuit state and provider-cache construction/clearing are racy;
  a killed child may not be reaped.

43 targeted lifecycle/planner tests and static checks passed; PR #129 CI was
reported passing.

### `w8-frontend-requests` — REVISE

- **P1:** New/delete/archive actions do not invalidate selection generation, so
  a late conversation load can overwrite a reset/new transcript.
- **P1:** Safe parsed `ChatApiError.message` is discarded.
- **P2:** Conversation create/list failures are outside handled visible state.

77 focused frontend tests and frontend static checks passed; PR #130 CI was
reported passing.

### `w9-frontend-polish` — REVISE

- **P1:** The `w8` selection-generation and safe-error-display defects remain.
- **P2:** Fallback template normalization accepts malformed nested rows that can
  throw during rendering.

The frontend suite (147 tests), lint, typecheck, format check, and build passed.
Remote PR metadata/checks were not available.

## Recommended repair and re-review order

1. Stabilize shared lifecycle primitives first: event-loop diagnostics,
   pending-turn cancellation, import process groups, active DB connection
   coordination, and LiteRT process identity.
2. Repair data correctness next: V2 child parsing/route roots/staging safety,
   then date bounds and unit policy. Re-run worker-invariance and adversarial
   import fixtures.
3. Repair cache and provider consistency: no fallback writes, numeric metric
   allowlist, single-flight cache behavior, and locked circuit/client lifecycle.
4. Repair frontend state/error contracts: conversation transition invalidation,
   visible structured failures, and recursive template validation.
5. Re-run each immediate-parent PR review, then run an integrated stack review
   from `main` through `w9`. Finally, verify GitHub bases, all 64 issue links,
   current CI, and review comments using a valid existing GitHub session.

No review verdict here is merge authorization.
