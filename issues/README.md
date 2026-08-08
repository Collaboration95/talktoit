# Issue drafts for the tti architectural audit (Aug 2026)

Each file is a ready-to-paste GitHub issue draft. Numbers `GH-1..GH-22` are the
**local placeholders** used throughout `AUDIT.md`; the real GitHub issue numbers
are listed below. The `AUDIT.md` mapping table has been updated to the real
numbers.

| File | Local ID | Priority | GitHub issue |
|------|----------|----------|--------------|
| gh-01-profile-cache.md | A-01 | high | [#14](https://github.com/Collaboration95/talktoit/issues/14) |
| gh-02-async-event-loop-blocking.md | A-02 | high | [#15](https://github.com/Collaboration95/talktoit/issues/15) |
| gh-03-sqlite-churn.md | A-03 | medium | [#16](https://github.com/Collaboration95/talktoit/issues/16) |
| gh-04-diagnostics-retention.md | A-04 | medium | [#17](https://github.com/Collaboration95/talktoit/issues/17) |
| gh-05-ranked-aggregate.md | A-05 | medium | [#18](https://github.com/Collaboration95/talktoit/issues/18) |
| gh-06-semantic-cache-order.md | A-06 | medium | [#19](https://github.com/Collaboration95/talktoit/issues/19) |
| gh-07-sqlite-wal.md | A-09 | medium | [#20](https://github.com/Collaboration95/talktoit/issues/20) |
| gh-08-engineering-doc-drift.md | A-14 | medium | [#21](https://github.com/Collaboration95/talktoit/issues/21) |
| gh-09-structured-logging-gap.md | A-12 | low | [#22](https://github.com/Collaboration95/talktoit/issues/22) |
| gh-10-jsdom-branch.md | A-10 | low | [#23](https://github.com/Collaboration95/talktoit/issues/23) |
| gh-11-popstate.md | A-11 | low | [#24](https://github.com/Collaboration95/talktoit/issues/24) |
| gh-12-app-state-version.md | A-13 | low | [#25](https://github.com/Collaboration95/talktoit/issues/25) |
| gh-13-intl-formatters.md | A-07 | low | [#26](https://github.com/Collaboration95/talktoit/issues/26) |
| gh-14-working-tree-hygiene.md | A-15 | low | [#35](https://github.com/Collaboration95/talktoit/issues/35) |
| gh-15-versioning-release.md | A-16 | low | [#27](https://github.com/Collaboration95/talktoit/issues/27) |
| gh-16-concurrency-test.md | T-01 | medium | [#28](https://github.com/Collaboration95/talktoit/issues/28) |
| gh-17-startup-telemetry-test.md | T-02 | low | [#29](https://github.com/Collaboration95/talktoit/issues/29) |
| gh-18-format-tests.md | T-03 | low | [#30](https://github.com/Collaboration95/talktoit/issues/30) |
| gh-19-abort-test.md | T-04 | low | [#31](https://github.com/Collaboration95/talktoit/issues/31) |
| gh-20-profile-cache-test-and-bench-marker.md | T-05 | low | [#32](https://github.com/Collaboration95/talktoit/issues/32) |
| gh-21-structured-logging.md | L-01 | low | [#33](https://github.com/Collaboration95/talktoit/issues/33) |
| gh-22-release-hygiene.md | L-02 | low | [#34](https://github.com/Collaboration95/talktoit/issues/34) |

Also in this folder:
- `testing-proposal.md` — the testing proposal (split, fast/parallel, typecheck,
  suite performance) mapped to issue IDs.
- `tooling-release-proposal.md` — the tooling & release proposal mapped to issue
  IDs.

Labels to apply where they exist in the repo: `performance`, `concurrency`,
`observability`, `testing`, `infrastructure`, `devtooling`, `docs`, `bug`,
`priority: high/medium/low`. Propose any new labels behind those.
