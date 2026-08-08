# GH-5 — Push ORDER BY/LIMIT into SQL for ranked workouts and coalesce period aggregates (medium)

## Labels
`performance`, `priority: medium`

## Summary
- `queries.get_top_workouts` runs `_SQL_TOP_WORKOUTS` with **no LIMIT**; it joins
  the whole distance subquery (`GROUP BY workout_id` over all distance
  `workout_statistics`) and returns every matching workout for the activity, then
  sorts all rows in Python and truncates to top-n. By default the window is the
  full history (1970–2100), so a large dataset transfers and sorts everything for
  a top-5 chart.
- `get_period_summary` issues 3 aggregate queries; `get_comparison` issues 6
  (2 periods × COUNT/SUM-distance/SUM-energy). These could be coalesced or
  expressed as a single grouped query.

## Locations
- `backend/app/db/queries.py` (`get_top_workouts`, `_SQL_TOP_WORKOUTS`, `_period_stats`, `get_period_summary`, `get_comparison`)

## Proposed direction (no code)
- Add `ORDER BY <metric val> DESC NULLS LAST LIMIT n` to `_SQL_TOP_WORKOUTS` with
  the metric projected in SQL, removing the Python sort and the full transfer.
- Consider one parameterized aggregate query (per metric) for period/comparison to
  replace the 3/6 separate executions.

## Acceptance
- A benchmark of ranked querys on the synthetic fixture shows no full-table
  transfer; top-N returns at most N+small padding rows.
