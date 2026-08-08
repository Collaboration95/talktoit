# GH-7 — SQLite app-state: shared file, no WAL/busy_timeout, concurrent writers (medium)

## Labels
`concurrency`, `priority: medium`

## Summary
All app-state and diagnostics SQLite access targets one file with Sudo
`sqlite3.connect(self.path)` — no `PRAGMA journal_mode=WAL`, no `busy_timeout` set
explicitly. The dashboard fires 8 parallel requests whose sync `def` handlers run
in the FastAPI threadpool and each call `safe_record` (writer) + `get_active`
(reader); combined with chat (GH-2) this creates concurrent writers on a
non-WAL database, risking `database is locked` errors and added latency under
load.

## Proposed direction (no code)
- Open the store with `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
  PRAGMA busy_timeout=<ms>`; set `sqlite3.connect(..., timeout=…)` explicitly.
- Serialize or batch the diagnostics writes (see GH-3) so writers don't collide.
- Optionally move diagnostics to its own SQLite file to decouple event-write
  contention from conversation/read state.

## Acceptance
- A concurrency test (GH-16) with parallel chat+dashboard requests completes with
  zero `database is locked` errors.
