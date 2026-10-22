# Final UX/analytics review corrections (#193 / #170)

Parent: `476bbd25e0cceb5202f6ab591c6e1ddde50313f5`. The original full review,
reproducer and observed JSON remain unchanged in
`/tmp/tti-final-20261023/reviews/ux-analytics{.md,-repro.py,-repro.json}`.

- F1: sleep accepts one complete supported date clause. Unsupported month spans,
  conflicting periods and partial dates return local `clarification_needed`.
  The existing explicit ISO/English ranges, relative calendar periods and named
  months remain supported; the date grammar is not expanded.
- F2: stages and category-specific duration requests return local `unsupported`
  guidance with a supported coverage example. Coverage still unions all category
  intervals under [the sleep decision](sleep-chat.md); it is not redefined as
  REM or asleep time. Neither remote planner nor narrator receives these questions.
- F3: Settings checks catalog-specific usable values, matching dashboard validity:
  non-null numeric values include true zero; categorical sleep uses text labels.
  Imported numeric rows with no numeric observations are `malformed`, so existing
  Chat guidance omits their starters. No frontend production change is needed.

Exact cache reads precede planning in HTTP and CLI. Cache v7 makes persisted v6
exact and canonical entries unreachable, preventing old incorrect sleep answers
from bypassing the new planner. Semantic history remains intact: reuse requires
an identical current tool/argument intent, and these unsupported questions now
produce fallback intents instead of sleep trends. Dataset identity, snapshots,
response envelopes and the coverage tool are unchanged.

Regression-first receipt: before production edits, focused Python 3.12.11 tests
exited **1**, with **36 failed / 79 passed**. Failures include all three accepted
findings, official-import HTTP/CLI reproductions and persisted v6 cache paths.
Log: `/tmp/tti-corrections-20261023/logs/red.log`. All verification uses synthetic
exports, absolute temporary DB/state/shard paths, denied Python TCP/private-file
access and mocked providers; pytest workers are capped at two. Full-suite
`TTI_LOCAL_AUTOSTART` remains unset. No performance benchmark is run.

Verification commands run through `/tmp/tti-corrections-20261023/run.py`, which
passes a minimal environment, pins Node 20.20.2 / Python 3.12.11, and installs a
Python audit guard. Log names below are relative to its `logs/` directory.

| Check | Exit / result |
| --- | --- |
| Initial static check | 1: SQL string construction flagged; replaced with two static queries |
| `green-focused.log` | 1: wrong helper import; corrected to `app.db.migrate` |
| `green-focused-2.log` | 0: 115 backend tests passed |
| `frontend-focused.log` | 1: new test expected `Steps` instead of the full `Available: Steps` label; selector corrected |
| `frontend-focused-2.log` | 0: 18 tests / two files passed |
| `backend-full.log` | 2: interrupted after 320 passes and stale v6 assertion; updated the two existing contract pins to v7 |
| `backend-quality.log` | 2: test en-dash literals flagged; equivalent Unicode escapes retained the exact test input |
| `backend-quality-2.log` | 0: `make lint-backend typecheck-backend check` passed |
| `backend-full-final.log` | 2: 1,046 passed, three worker-default assertions failed because the verification wrapper set `TTI_INGEST_WORKERS=2` |
| `environment-recheck.log` | 0: all six affected tests passed after removing that wrapper override; pytest still uses two workers |
| `backend-full-clean-env.log` | 0: `make test-backend`, 1,049 passed; overall coverage 89.55% |
| Module coverage | Initial unquoted glob rejected by zsh (1); quoted commands below passed (0), ingestion 92%, LLM 86% |
| `original-repro.log` | 0: original reproducer, HTTP/CLI agreement in all five cases, zero provider calls |

Backend quality includes Ruff formatting/lint, Pyright, frontend lint/types/format
and version consistency. The changed frontend test file also passes Prettier.
No frontend production source or types changed, so the full frontend suite is
left to combined acceptance. The original review is preserved with SHA-256
`3ac93ed4be67b4ffc886ec29f8e13e45808287738fdc11e8ed9b53433c0edce4`.

The successful module commands were `uv run --directory backend coverage report
--include='app/ingest/*' --fail-under=90` and the same command with
`--include='app/llm/*' --fail-under=70`. Their logs are `coverage-ingest.log` and
`coverage-llm.log`. `git diff --check` passes. The full suite was rerun only after
the recorded contract-pin failure and then the worker-environment failures.

Behavioral oracles: unsupported June-to-July wording clarifies locally; the
complete ISO June 1–July 31 control still reports June 1 = 3 hours and July 1 =
4 hours. The separate June stage endpoint still reports Core = 1 hour, REM =
0.5 hour, asleep union = 1.5 hours. Stage requests do not substitute the 3-hour
coverage result. Imported `value="missing"` has zero numeric observations and
Settings/dashboard both report `malformed`; imported `value="0"` remains
`available` and yields a measured zero. Categorical sleep has zero numeric
observations, four text labels, and remains `available`. Current UI tests omit
the Steps label/starter for `malformed` and retain both for `available`.

Parent-owned remaining acceptance: integrate all review corrections, run the
combined synthetic browser journey and CI/build, obtain a new independent review
with the original brief/findings/responses at the combined head, and run any
needed quiet performance gate. Future-main #176/#199 acceptance is not established
by these local checks. No standalone PR, issue update, CI watcher or merge is part
of this correction branch.
