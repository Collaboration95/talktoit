# GH-4 — Unbounded `diagnostics_events` table and full-table `aggregate()` (medium)

## Labels
`observability`, `performance`, `priority: medium`

## Summary
`diagnostics_events` has no retention/eviction policy. On a long-lived local app
every chat request, dashboard panel, query, and import appends at least one row
per call, so the table grows without bound. `aggregate()` then issues
`SELECT category, status, duration_ms, … FROM diagnostics_events` with **no
window** and `fetchall()`s the entire table into memory to compute counts, mean,
and p95, so the Diagnostics view's memory cost grows linearly with the stored
history.

`MAX_RECENT_LIMIT` only caps reads, not storage.

## Locations
- `backend/app/state/diagnostics.py` (`record`, `aggregate`, `recent`)
- `backend/app/api/diagnostics.py`; `backend/app/cli/diagnostics.py`

## Proposed direction (no code)
- Add retention: a bounded count and/or TTL (e.g. keep newest N=5k and/or 30d),
  enforced on `record` or an idle sweep.
- Make `aggregate()` aggregate in SQL (`GROUP BY category, status`, `avg`/`percentile`)
  instead of loading every row; drop `durations_by_category` to `fetchall` only the
  needed columns, or do the percentile in SQL.

## Acceptance
- The events table stays below the retention bound on a long-running install; the
  Diagnostics view memory is bounded and its latency constant in history size.
