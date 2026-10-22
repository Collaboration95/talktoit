# Decision: explicit comparisons for steps, resting HR, and HRV

**Status:** Accepted for implementation in TTI-A-004 (#195)
**Scope:** Compare steps, resting heart rate, and HRV SDNN over two explicit local
date periods. This is a descriptive comparison of imported measurements, not a
medical or causal interpretation.

## Existing behavior and reusable contracts

`metric_catalog.py` declares steps as `count`/sum, resting HR as `bpm`/average, and
HRV SDNN as `ms`/average. `get_trend` reads non-null numeric values by Apple Health
type, uses Asia/Singapore local dates, sums steps in each bucket, and averages
resting-HR/HRV observations in each bucket. It does not filter by source, so
comparisons must use the same all-imported-source scope and must not silently pick a
device or de-duplicate source rows.

The existing `get_comparison` is workout-only: it compares period totals for
sessions, distance, duration, and active energy. Its Pydantic model and TypeScript
type already allow nullable values and its renderer already displays `—` for nulls.
Keep those fields and existing workout rows decodable.

## Decision

Accept two explicit, inclusive local date ranges and compare only measurements
inside each range. Require both ranges; do not infer an implicit “before/after”
window. Use Asia/Singapore for converting local midnight bounds to UTC and assigning
records to local calendar days. All imported sources participate, matching the
existing trend query.

Use these period values:

| Metric | Period value | Unit | Observed day |
| --- | --- | --- | --- |
| Steps | Mean of the daily step sums over days with at least one numeric step record | `steps/day` | A local day with one or more non-null step rows; sum all those source values for that day first |
| Resting HR | Arithmetic mean of all non-null resting-HR observations in the period | `bpm` | A local day with one or more non-null resting-HR rows |
| HRV SDNN | Arithmetic mean of all non-null HRV SDNN observations in the period | `ms` | A local day with one or more non-null HRV rows |

Daily step sums use the existing trend's source-row sum. Averaging those daily sums
over observed days avoids making an unequal-length period look larger only because
it contains more calendar days. Resting HR and HRV retain the catalog's observation
average (sample-weighted, not an average of daily averages); their values are not
scaled by period length. Show observed and requested days beside each value so users
can see coverage differences.

Requested days are the inclusive calendar-day count in that period. Observed days
count distinct local dates containing at least one non-null numeric row for that
metric. Missing days are never filled with zero. A true numeric zero remains a
measurement and its day counts as observed. If a period has no observations, its
value is null. If either side is null, delta is null and direction is neutral/flat;
do not subtract an absent value as zero. If both sides have no observations, both
values and delta are null. When both values exist, `delta = this - prior` in the
metric's displayed unit.

Display signed numeric change with a neutral label such as `Change` and neutral
coloring. “Up” and “down” may describe arithmetic direction internally, but must not
be presented as better/worse, improvement/decline, risk, or a causal explanation.
Do not compute percentage change: it is undefined for a zero baseline and obscures
the different metric units.

## Backward-compatible payload and validation

Extend the existing `comparison` payload rather than introducing a new template.
Keep the current title, period labels, `metrics`, and required row fields intact.
Add optional per-row metadata for the new metric rows:

```json
{
  "label": "Steps per observed day",
  "this_value": 8000,
  "last_value": 5000,
  "delta": 3000,
  "unit": "steps/day",
  "direction": "up",
  "this_observed_days": 4,
  "this_requested_days": 7,
  "last_observed_days": 2,
  "last_requested_days": 3,
  "value_basis": "observed_day_mean",
  "direction_tone": "neutral"
}
```

The four day counts are nullable/optional and `value_basis` and
`direction_tone` are optional, so existing workout payload producers and consumers
remain valid. For new metric rows, populate the day counts, use `observed_day_mean`
for steps and `observation_mean` for resting HR/HRV, and set neutral direction tone.
Update the TypeScript interface and renderer to show coverage (for example
`4/7 days`) and neutral signed changes; do not add an HRV dashboard panel.

Add `metric_ids` to the validated comparison input, restricted to the three
catalog IDs `steps`, `resting_hr`, and `hrv`. Omitted `metric_ids` preserves the
existing workout comparison behavior. Reject unsupported IDs, inverted ranges, and
missing dates at the local tool boundary; a request can include one or more of the
three metrics. Use the registry and `get_comparison` query path with catalog-owned
labels, units, and aggregation policy. Keep SQL parameterized and use only catalog
metric IDs to select record types.

## Deterministic question vocabulary

Recognize explicit forms such as:

- “Compare my steps from 1–7 June 2026 with 8–14 June 2026.”
- “Compare resting HR and HRV from 2026-06-01 to 2026-06-07 vs 2026-05-25 to 2026-05-31.”
- “Compare steps, resting heart rate, and HRV between June 1–7 and May 25–31, 2026.”

Require two complete, unambiguous date ranges and at least one supported metric.
If a range is missing, a year is ambiguous, or the question asks for an unsupported
metric, ask for the exact two ranges or use the normal local fallback. Do not send
the documented patterns to a remote planner. Preserve the existing deterministic
workout comparison path for workout language.

## Executable examples

1. **Unequal range and coverage:** June 1–7 has step records on four days, with
   daily totals 4,000, 8,000, 10,000, and 10,000. Its displayed value is 8,000
   steps/day and coverage is 4/7. May 25–27 has records on two days, 4,000 and
   6,000. Its value is 5,000 steps/day and coverage is 2/3. Delta is +3,000
   steps/day, alongside coverage; the app does not fill the missing days with zero.
2. **No data on one side:** if the prior period has no resting-HR rows and the
   current mean is 61 bpm, show current 61 bpm, prior `—`, its observed/requested
   day coverage, prior coverage `0/y`, and null delta. Do not report +61 bpm.
3. **No data on both sides:** both values and delta are null; both coverage counts
   are zero. Keep the comparison row and show missing values as `—`.
4. **Measured zero:** if a step day has numeric rows summing to zero, it is an
   observed day and participates as zero in the mean. It is distinct from a day
   with no step rows, which is missing.
5. **Mixed metrics/sources:** a request may compare steps and HRV together. Each
   uses its own valid records and observed-day counts. All imported sources
   contribute; there is no source matching requirement between periods or metrics.

## Bounded implementation checklist for #195

1. Add catalog-validated comparison input and a query that computes daily step sums,
   observed-day step means, and period observation means for resting HR/HRV in local
   date windows. Return nulls and distinct-day coverage exactly as specified.
2. Add typed optional coverage/basis/tone fields while retaining existing workout
   payload fields and default behavior. Extend the comparison renderer and shared
   metric formatting for `steps/day`, `bpm`, and `ms` with neutral health-metric
   direction styling.
3. Add deterministic parsing for the explicit vocabulary above and local
   clarification for incomplete or ambiguous ranges. Keep CLI and HTTP on the
   shared chat orchestrator; no hosted planner is needed for these forms.
4. Cover query arithmetic, source scope, local-day boundaries, unequal/missing
   periods, true zero, mixed metrics, invalid IDs/ranges, legacy workout payload
   decoding, and renderer coverage/null/delta states with synthetic data.

Do not invent an HRV dashboard panel, normalize by a clinical range, infer causes,
or describe a numeric change as a health outcome.
