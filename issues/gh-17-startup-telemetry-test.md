# GH-17 — Startup-telemetry contract test (catches GH-12) (low)

## Labels
`testing`, `priority: low`

## Summary
The app stores a Diagnostics startup event in `main.py` (versioned schema fields)
but no test asserts its values. This is exactly how the stale
`app_state_version: "7"` (GH-12) escaped. Add a test that runs the lifespan and
asserts the recorded `app_state_version` equals the store's current
`PRAGMA user_version` `max`, and that the startup event conforms to the
diagnostics allowlist.

## Locations
- `backend/tests/unit/test_diagnostics.py` (extend) or a new
  `backend/tests/integration/test_app_startup.py`
- `backend/app/main.py`, `backend/app/state/app_state.py`

## Acceptance Criteria
- Test fails if the hardcoded/derived `app_state_version` mismatches the store's
  max `user_version`; passes once GH-12 is fixed.
