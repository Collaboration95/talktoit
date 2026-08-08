# GH-3 — Per-request SQLite churn: every accessor re-runs `migrate()` and opens two connections (medium)

## Labels
`performance`, `priority: medium`

## Summary
`AppStateRepository` instantiated per handler; **every accessor**
(`get_active`, `get_conversation`, `get_turns`, `get_cached_response`,
`put_cached_response`, `create_pending_turn`, …) first calls `self.migrate()` —
which opens its own connection, runs `PRAGMA user_version`, and checks the DDL
chain — then opens a second connection for the real work. `DiagnosticsRepository`
similarly runs `CREATE TABLE IF NOT EXISTS` and opens a connection on **every**
`record()` call, and the hot-path callers pass `repository=None` so a brand-new
repository is constructed per event.

A single chat request therefore performs on the order of 16+ SQLite
connect/close operations plus repeated migration checks, all synchronously on the
event loop (see GH-2).

## Locations
- `backend/app/state/app_state.py` (`AppStateRepository._connection`, `migrate`, accessors)
- `backend/app/state/diagnostics.py` (`DiagnosticsRepository._connection`, `migrate`, `record`)
- `backend/app/api/chat.py` / `backend/app/llm/orchestrator.py` (`safe_record(...)` / `timed_record(...)` with `None`)

## Proposed direction (no code)
- Run the store-migration once at startup (lifespan) and drop per-accessor
  `migrate()` calls.
- Reuse one app-owned `AppStateRepository` / `DiagnosticsRepository` instance
  (process scope) instead of constructing on each call, and thread it through the
  orchestrator instead of passing `None`.
- If writes must stay per-request, batch the pending diagnostics events and flush
  once per request rather than one connection per event.

## Acceptance
- A chat request opens a small, bounded number of SQLite connections; a
  micro-benchmark shows the request's sqlite syscalls drop by an order of magnitude.
