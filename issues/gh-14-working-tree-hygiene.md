# GH-14 — Working-tree hygiene: untracked `audit-1/` and modified `.gitignore` (low)

## Labels
`chore`, `priority: low`

## Summary
On branch `audit/fixes` (== `main` at `f9e6612`):
- `audit-1/` (July 2026 review docs) is entirely untracked — it appears in
  directory listings and find results but is not in git, so it can silently
  diverge or be lost, and its large planning tree is not covered by any policy.
- `.gitignore` has an uncommitted modification (adds `.pi/`).

## Proposed direction (no code)
- Decide and commit: either commit `audit-1/` (e.g. under `docs/audit-1/`) or
  gitignore it explicitly; commit the `.gitignore` change with a message.
- Confirm `.pi/` (agent memory) is ignored if it should stay local.

## Acceptance
- `git status` on `audit/fixes` is clean or the remaining deltas are intentional
  and committed.
