# GH-1 — Cache the data-profile computation (dataset-scoped) (high)

## Labels
`performance`, `priority: high`

## Summary
`get_data_profile(conn)` executes three full-table DuckDB scans per call
(`_SQL_COVERAGE` MIN/MAX over `records`+`workouts`+`activity_summaries`,
`_SQL_WORKOUT_TYPES` GROUP BY over all workouts, `_SQL_AVAILABLE_METRICS`
DISTINCT over records). It is recomputed:

- twice per chat request — once in `api/chat.py` (line ~100) and again inside
  `ChatOrchestrator.answer` (`llm/orchestrator.py` line ~210);
- twice per dashboard endpoint — `_resolve_window` and `_resource_metadata`
  (`api/dashboard.py`), so a full 8-panel dashboard load performs ~12–14
  identical scans against a ~137 MB DuckDB;
- and `resolve_activity_type` (`db/data_profile.py`) re-runs `_SQL_WORKOUT_TYPES`
  for every chat tool that resolves an activity name.

The result is a deterministic function of the active dataset (`DatasetVersion.id`
/ `content_hash_prefix`), so all this work is pure redundancy.

## Locations
- `backend/app/db/data_profile.py` (`get_data_profile`, `resolve_activity_type`)
- `backend/app/api/dashboard.py` (`_resolve_window`, `_resource_metadata`)
- `backend/app/api/chat.py`; `backend/app/llm/orchestrator.py`

## Proposed direction (no code)
- Cache the `DataProfile` in a process-level dict keyed by the active
  `DatasetVersion.id` (or content-hash prefix), invalidated on activation /
  deletion.
- Hoist `resolve_activity_type` resolution to reuse the cached workout-type
  table instead of re-querying per tool.
- Make the cache injectable so the headless CLI (which owns its own repository)
  can reuse it; guard with a revalidation test (see GH-20).

## Acceptance
- A dashboard load performs exactly one profile computation; a chat request at
  most one; the cache is invalidated when a new dataset is activated.
