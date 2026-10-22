# Daily-use guidance acceptance evidence

Scope: #170, #171, #173, #174, #175 and #197, as one batch targeting
`codex/dev-roadmap-20261022`. This is implementation evidence for the parent's
integrated review, not an integration receipt or independent approval.

## Observable acceptance

- First import: Chat links directly to the existing Settings importer, explains
  Health → profile → Export All Health Data and unpacking the ZIP, and makes
  supported local questions model-optional. Starters use existing Settings metric
  states and dataset workout counts. Steps-only, workouts-only, unsupported-metric,
  loading failure/retry and return-from-import cases are tested.
- Imports: Settings rediscovers process-local jobs with GET /api/imports. Polls
  abort on unmount; superseded responses cannot replace cancellation or newer
  uploads. Cancellation reconciles terminal races with GET. Failure, cancellation,
  successful completion, missing jobs and cancellation failure remain distinct.
  Only actual job states appear; no estimated percentage or invented phase.
  Missing counts are unavailable, not zero; route counts mean references, not GPS
  geometry. Native File upload avoids Chrome's duplex requirement for raw streams.
- Chat: the existing fallback template gains an optional validated reason.
  Unsupported pace ranking offers duration ranking; no-match results offer scope
  recovery; ambiguity asks for detail/selected-answer context; provider failure
  points to Settings and supported local questions. No generic model-start remedy
  is attached to unsupported results. HTTP and CLI JSON retain ChatResponse and
  template validation. Untrusted provider fallback prose is replaced locally.
- Privacy: saved effective configuration drives the displayed mode and egress.
  Hosted planning includes question text and dataset metadata; narration includes
  question text and compact rounded facts. Raw rows and route geometry remain
  excluded. Local provider overrides a previously stored hosted mode for display.
- Readiness: both Settings endpoints use the same one-second local health probe
  off the event loop, with the gateway's loopback boundary checked before probes.
  The selected effective model/endpoint match chat. Available, stopped, missing
  model, timeout/error, external endpoint, blocked probe and non-loopback cases
  use stubs. Hosted health makes no external request. Public probe failures omit
  exception text and private filesystem status fields.
- Routes: available geometry retains its chart/facts/download; missing and invalid
  routes explain absence without a broken download action. XML upload instructions
  disclose missing companion GPX support before file selection and refer only to
  the existing local XML+companion-folder import command.

## Verification

Runtime: Node 20.20.2, Python 3.12.11. Locked dependencies synced after merging
maintenance dev `475e67347a1fce1c8fe7be96143782f276923c38`, then dashboard dev
`82c42bf40f48e7897cad27f035eb47c14bbda5eb`. Thresholds are unchanged.

- Regression tests were written and observed failing before their implementation.
- Focused backend contracts plus chat/planner/gateway/model tests: 57 passed, exit 0.
- Focused native upload/import UI tests: 23 passed, exit 0. Final Settings suite:
  10 passed on Vitest 4.1.12, exit 0.
- `PYTEST_XDIST_AUTO_NUM_WORKERS=2 make check-full` on maintenance dev: exit 0;
  512 backend tests, 181 frontend tests. Backend overall 87.61%, ingestion 91%
  and LLM 83%. No backend files changed in the later dashboard-only merge.
- After that merge and the final Settings disclosure fix: `make check`, exit 0;
  `npm --prefix frontend run test:coverage`, 196 tests in 29 files, exit 0;
  `npm --prefix frontend run build`, exit 0.
- Actual Vitest 4 coverage: statements 88.45% (1142/1291), branches 78.38%
  (939/1198), functions 90.43% (350/387), lines 91.45% (1027/1123).

## Browser evidence and limits

A separate server on 127.0.0.1:8027 used temporary synthetic storage, denied all
model execution and stubbed local probes. DOM interactions verified first-import
navigation, pre-upload XML/GPX disclosure, native upload of a 298-byte steps XML,
job success with one record (1200 steps on 5 June 2026), refreshed steps-only
starters after returning to Chat, and a rendered trend canvas with the question
still visible. Hosted form edits retained the old saved Privacy state until Save;
saved narration mode explicitly listed question text and rounded measurements.

`preview_snapshot` failed with `Preview automation snapshot timed out after
15000ms.` Evidence used `preview_evaluate`; no screenshot or pixel-level review is
claimed. Cancel/reentry races and all route states have synthetic component/API
coverage; the full integrated browser matrix remains the parent's acceptance work.
No hosted requests, real model processes, personal data or performance claims.

Import jobs still belong to the running backend process. Durable restart recovery,
activation/deletion, CLI implementation and dataset leases remain their owners'
scope. The only gateway change exports the existing loopback predicate for reuse;
its behavior is unchanged. A route integration test now creates a fresh app to
avoid stale lifespan repository state from earlier tests. CI checks and independent
integrated review are pending at PR creation; this agent does not poll or merge.
