# GH-16 — Concurrency integration test: parallel chat + dashboard against shared SQLite (medium)

## Labels
`testing`, `concurrency`, `priority: medium`, `test-coverage`

## Summary
There is no test that drives the concurrency the app is expected to tolerate: the
dashboard fires 8 parallel requests (threadpool `def` handlers) while a chat
request runs, all sharing one SQLite store (GH-7) and one event loop (GH-2). A
test should catch `database is locked` errors, event-loop serialization that
stalls other requests, and any interleaving that corrupts diagnostics/state.

## Proposed direction (no code/tests)
- Extend a `TaskGroup`-based integration test in `backend/tests/integration/`
  that, against the synthetic fixture and a `tmp_path` store:
  - issues 2–3 chat requests and the full dashboard panel set concurrently,
  - asserts no `database is locked`, no 500s, and that each response's dataset
    scope and cache behavior are correct,
  - optionally asserts wall-clock scales better than fully serialized.
- Reuse the existing `tmp_path`, in-memory/in-file store fixtures.

## Dependencies
Blocks/validates GH-02 and GH-07.
