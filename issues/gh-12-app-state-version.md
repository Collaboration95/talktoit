# GH-12 — Startup telemetry hardcodes `app_state_version: "7"` while the store migrates to v8 (low)

## Labels
`bug`, `observability`, `priority: low`

## Summary
`backend/app/main.py` lifespan records `"app_state_version": "7"` as a literal,
but `AppStateRepository.migrate()` now migrates to `PRAGMA user_version = 8`
(v8 added `turns.normalized_question`). The Diagnostics "app" event therefore
mislabels the live schema version, and any consumer trusting that field gets a
wrong value. The same literal would drift again on the next migration.

## Locations
- `backend/app/main.py` (lifespan startup event)
- `backend/app/state/app_state.py` (`migrate`, max version = 8)

## Proposed direction (no code)
- Derive the version from the store (e.g. `PRAGMA user_version` via the repository)
  or export a `SCHEMA_VERSION` constant from `app_state` and reference it.

## Acceptance
- The startup event reports the same version the store migrated to; a contract
  test asserts it (see GH-17).
