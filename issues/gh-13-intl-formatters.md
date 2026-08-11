# GH-13 — `format.ts` constructs a new `Intl.*Format` per call/bucket (low)

## Labels
`performance`, `priority: low`

## Summary
`frontend/src/lib/format.ts` creates a fresh `Intl.NumberFormat` inside every
`formatNumber` call and a fresh `Intl.DateTimeFormat` inside
`formatBucketLabel`/`formatChartBucketFullDate` per bucket. Chart label loops
therefore construct formatters once per point per render — `Intl` construction is
one of the more expensive JS operations, and health series can be hundreds of
points rendered repeatedly.

## Locations
- `frontend/src/lib/format.ts`

## Proposed direction (no code)
- Module-level memoized formatter factory keyed by (fractionDigits, style) and
  reuse it; keep behavior identical (verified by the existing `format.test.ts`).

## Acceptance
- Existing `format.test.ts` passes unchanged; a render of a 365-point series
  constructs formatters O(1) times.
