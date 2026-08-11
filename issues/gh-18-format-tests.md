# GH-18 — Extend formatting-label and sparse-series tests (low)

`)

## Labels
`testing`, `priority: low`

## Summary
`lib/format.test.ts` covers basic helpers. Gaps:
- `formatBucketLabel`/`formatChartBucketFullDate` lack year-boundary cases
  (ISO week `2026-W52` vs `2027-W01`, and `includeYear` disambiguation across a
  year boundary).
- No test asserts behavior with sparse/empty series (missing buckets render `None`
  without throwing) across day/week/month granularities.

## Locations
- `frontend/tests/lib/format.test.ts`

## Acceptance Criteria
- New cases for year-boundary week buckets and sparse series pass; existing cases
  unchanged.
