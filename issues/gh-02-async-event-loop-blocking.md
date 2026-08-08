# GH-2 — Chat handler runs blocking DuckDB/SQLite work on the async event loop (high)

## Labels
`concurrency`, `performance`, `priority: high`

## Summary
`POST /api/chat` (`backend/app/api/chat.py`) is an `async def` handler but runs
all local data work synchronously on the event loop: `get_data_profile`,
`plan_local_question`, every `AppStateRepository` read/write, the tool
`dispatch_tool` (DuckDB), and each `safe_record`/`timed_record` diagnostics
write. Only the provider-gateway `complete()` call is awaited. A slow aggregate on
a large local DB blocks the entire loop, serializing every other request
(health checks, dashboard calls that hit the loop-adjacent threadpool, second chat
request) behind it.

## Locations
- `backend/app/api/chat.py` (`chat` handler)
- `backend/app/llm/orchestrator.py` (`answer`, `_dispatch_tool`)
- `backend/app/state/app_state.py` / `backend/app/state/diagnostics.py` (all sync)

## Proposed direction (no code)
- Keep the handler async but offload the DB/state work with
  `starlette.concurrency.run_in_threadpool` (or `asyncio.to_thread`) around the
  local computation, leaving only the gateway await on the loop; or
- Convert the endpoint to a sync `def` handler (FastAPI runs it in the
  threadpool) and keep the orchestrator's internal await via the gateway.
- Ensure CLI `app/cli/chat.py` and integration tests share the same fixed path.

## Acceptance
- Two concurrent chat requests + a dashboard load complete without one blocking
  the others; a benchmark of event-loop stalls drops to ~0 during local queries.
