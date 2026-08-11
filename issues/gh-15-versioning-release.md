# GH-15 — No CHANGELOG/version-bump policy or distributable build verification (low)

## Labels
`infrastructure`, `priority: low`

## Summary
Version numbers are consistent (`pyproject.toml` 0.1.0, `package.json` 0.1.0,
`main.APP_VERSION` 0.1.0) — good. But there is no `CHANGELOG.md`, no automation to
detect version drift across the three declared sources, and no CI step that
builds/verifies a distributable artifact (CI builds the frontend via
`npm run build` but nothing packages or asserts a backend bundle for a local
self-host install; there is no signed/attested release — appropriate for a
local-first app as long as the checklist row is honest `n/a`).

## Locations
- `backend/pyproject.toml`, `backend/app/main.py` (`APP_VERSION`),
  `frontend/package.json`, `.github/workflows/ci.yml` (`build` job)

## Proposed direction (no code)
- Add a root `CHANGELOG.md` and a CI assertion that the three version sources
  agree.
- Add an optional `make dist` that builds the frontend and emits a tagged manifest,
  gated by an explicit checklist row stating that no signing/attestation is
  claimed. See the tooling proposal GH-22.

## Acceptance
- Version sources are checked to agree in CI; a `make dist` target exists and is
  documented.
