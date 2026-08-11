# GH-22 — Release/versioning hygiene: CHANGELOG, version-consistency gate, optional dist (L-02) (low)

`)

## Labels
`infrastructure`, `priority: low`

## Summary
Add a lightweight release/versioning baseline that doesn't over-engineer a
local-first app:

- a root `CHANGELOG.md` is tracked,
- a CI check asserts `pyproject.toml` project.version, `frontend/package.json`
  version, and `backend/app/main.py` `APP_VERSION` agree (closes the drift window
  opened by GH-15),
- an optional `make dist` builds the frontend and emits a tagged manifest, and the
  release checklist row for signing/attestation is honest `n/a` (no bundled
  binary/signing is claimed).

## Locations
- `Makefile`, `.github/workflows/ci.yml`, repo root (CHANGELOG)

## Acceptance
- CI fails if versions disagree; `make dist` produces a deterministic bundle;
  the checklist declares signing `n/a` explicitly.
