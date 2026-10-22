# Final round-2 sleep UX corrections (#193 / #173)

Implementation base: `5c21941bdfa817d988cae84c3a8714536b7a3659` (PR #213).
The complete #193/#173/#199 contracts, #192 decision, engineering/style rules,
original round-1 review and both responses, full round-2 UX report and its three
reproducers were read. Prior reports and responses remain immutable. This is
implementation evidence for parent integration and independent round-3 review.

## R2-F2: one stage/category boundary

`_is_sleep_category_question` supplies the shared vocabulary for local sleep
classification and unsupported-measurement planning. Existing orchestrator,
planning projection and narration projection guards already call
`is_sleep_question`, so no provider projection or gateway change is required.
NREM, non-REM and expanded non-rapid/rapid eye movement spellings, REM, stages,
categories and the existing asleep/awake/in-bed vocabulary resolve locally,
with or without the word sleep. Deep/core/light requests also resolve locally;
an explicit workout activity retains its non-sleep meaning when sleep is absent.
Standard dash variants are normalized for this category predicate.

These requests return useful `unsupported` guidance with an interval-coverage
example. They never execute coverage as the requested stage measurement. The
existing coverage explanation may still name included awake/in-bed records.
This is a bounded known vocabulary, not a claim to recognize every English
paraphrase. Stage endpoint calculations and measured coverage are unchanged.

## R2-F1: consume the request and complete date clause

The sleep parser now full-matches a bounded request prefix and the entire
remaining date clause. It no longer searches for the first recognizable month
or relative period. Supported show/plot/chart sleep requests and the existing
bounded question forms retain explicit from/between ISO/English ranges,
dataset-anchored relative calendar periods and named month/year scopes.
Unconsumed bare days, day ranges without from/between, ordinals, weekdays,
leading singleton dates and conflicting periods clarify locally. There is no
new date grammar or inferred day scope.

The official V2 CLI import fixture contains June 1 coverage = 3 hours, June 15 =
2 hours and July 1 = 4 hours. Supported June 1–7 ISO and English controls return
only June 1; a supported June month control returns June 1 and June 15. Unsupported
leading fragments return `clarification_needed` in both actual HTTP and CLI paths.
The separate June 1–7 stage oracle remains Core = 1 hour, REM = 0.5 hour and
asleep union = 1.5 hours. Coverage is not substituted for any of those facts.

## Persisted cache and privacy boundaries

Cache version moves from v7 to v8. Dataset identity, snapshot marker and all other
key-envelope contracts remain unchanged. Existing intentional unit/benchmark
version pins move together; the persisted v6 regressions are unchanged. New
durable v7 exact/canonical tests verify the old entry remains readable under its
old key while its current key misses. A fresh app/repository and both HTTP/CLI
must return the corrected guidance. Semantic tests retain the exact old history
bytes and reject replay because the current fallback intent differs from the old
coverage tool. No cache/history deletion or schema migration is introduced.
Parent-owned shared engineering text still names its prior v7 receipt; this
document records the new v8 contract without rewriting that historical evidence.

The HTTP/CLI tests persist hosted planning-and-narration configuration and inject
a collecting mock gateway. Every tested stage variant requires zero gateway
planning/narration method calls and zero client completion calls, plus planning
and narration projection rejection. An unresolved non-sleep control records two
mock planning calls (HTTP and CLI), proving the collector remains active. No real
provider runs. Regression transport is independently denied by the existing
full-suite hook; gateway mock methods are preserved.

## Reproducible verification

Artifacts: `/tmp/tti-r2-ux-corrections-20261023/`. Its `run.py` uses a minimal
environment, absolute disposable DB/state/shard paths, CPython 3.12.11, Node
20.20.2, two pytest workers and the existing full-hook. It does not inherit
global autostart, stop-on-exit or ingest-worker overrides. Dependency environments
are reused read-only after confirming both committed lock hashes match.
Runtime catalog confirms `gpt-6.1-sol`, xhigh effort and priority service.

- Tests preceded production changes on exact candidate source: `red.log`, exit
  **1**, **61 failed / 32 passed**. These include wrong imported trend responses,
  missed aliases/projection boundaries and persisted v7 replay. Later test
  additions strengthen the live collector control and explicit v7 key misses.
- `green-focused.log`: exit **0**, **233 passed**. Final strengthened focus:
  `green-final-focused.log`, exit **0**, **235 passed**. Command: `uv run
  --directory backend --no-sync pytest -o addopts='' --no-cov -n 2 -q` over
  `unit/test_sleep_intent_round2.py`, `integration/test_sleep_intent_round2.py`,
  `unit/test_local_planner.py`, `unit/test_chat_cache.py`,
  `integration/test_review_corrections.py`, `integration/test_sleep_metric_chat.py`,
  `unit/test_provider_redaction.py` and `unit/test_provider_gateway.py` (all under
  `tests/`). This retains original F3 malformed/zero/category and v6 controls.
- `lint-focused.log`: exit **0**, Ruff check of changed production/new test files.
- `make-check.log`: `make check`, exit **0**: backend formatting/lint/Pyright,
  frontend lint/types/format and version consistency.
- `privacy-smoke.log`: exit **0**. Explicit synthetic `.env`/personal-assets
  reads, TCP, DNS and actual SDK completion entry were denied before access or
  transport; these deliberate attempts have a separate `private-smoke/` receipt.

The stable backend app tree is `ecf57fc8ebd5e313dd935b51176b5651a15e31e3`;
backend tests tree is `2f1b2579deef1b6237143f63291cf4ec19ad54dd`. Frontend source
and tests remain unchanged. The standalone `make test-backend` was already running
when the parent coordinated the combined gate; it will finish on this unchanged
source, with its final result in `backend-full.log` and the handoff receipt.
Module coverage receipts are external to the source commit too.

No formal timed benchmark, browser acceptance, real health-data read, hosted
inference, CI polling or new PR is part of this lane. The parent combines this
commit with the independent safety correction and owns one final combined
`make check-full`, CI/build/browser qualification and fresh independent round-3
acceptance. No issue/gate completion is claimed here.
