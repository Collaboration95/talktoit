# GH-8 — ENGINEERING.md stale vs the running tree (medium)

## Labels
`docs`, `priority: medium`

## Summary
`docs/ENGINEERING.md` no longer describes the committed reality:

1. §2.4 states ingest-90% / llm-70% are *“goals, tracked manually — not enforced”*
   and shows a “if we later want these enforced, add a CI step” snippet. In fact
   `ci.yml` `test-backend` and `make check-full` now run
   `coverage report --include="app/ingest/*" --fail-under=90` and
   `--include="app/llm/*" --fail-under=70`. The document describes the old state.
2. §6 documents a pre-commit `no-commit-to-branch` hook (blocks pushes to `main`)
   that is **not** present in the committed `.pre-commit-config.yaml`.
3. §1 layout and `docs/planning/README.md` name `docs/DISCOVERY.md` as the
   “source of truth” decisions log, but that file does not exist in the tree or in
   git (only ENGINEERING, HEALTH_DATA_UI_STYLEGUIDE, LLM_CLI_AND_TOOL_RESILIENCE_PLAN,
   SPEC, and planning/README are committed under `docs/`).
4. §4’s Makefile catalog omits the targets actually present (`check`, `check-full`,
   `run-cli`, `groq-smoke`, `status`, `diagnostics`, `bench`, `verify-headless`,
   `test-bk`/`test-fe`).

Per audit policy the committed reference/check-in truth wins; the stale doc itself
is the finding.

## Proposed direction (no code/rationale)
- Update ENGINEERING.md §2.4 to state the gates are CI-enforced.
- Either restore `no-commit-to-branch` in pre-commit (and document why it was
  removed if intentional) or drop the claim from §6.
- Add `docs/DISCOVERY.md` (or fix the pointer in `docs/planning/README.md`) so the
  “source of truth” reference resolves.
- Refresh §4 with the current Makefile surface; add a doc-drift CI check if
  feasible.
