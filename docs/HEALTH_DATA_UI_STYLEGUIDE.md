# Health Data UI Style Guide

This guide standardizes how health data is shown in the app and how result
payloads are prepared for the narrator LLM.

## Presentation Rules

- Show human-friendly values only.
- Round durations to whole minutes.
- Use at most one decimal place for distance in kilometers.
- Round heart rate, energy, elevation, and session counts to whole units.
- Never surface raw machine precision like `61.05181868268979`.
- Use Singapore time for workout timestamps and date ranges.
- Prefer explicit date labels like `8 Jun 2026` over raw ISO strings.
- Keep empty and error states actionable. Avoid dead-end messages.
- Do not echo raw fallback questions as primary content.

## Copy Rules

- Prefer concise summary text above structured metrics.
- When a result cannot be answered, say what happened and how to recover.
- Keep labels short and specific: `Duration`, `Distance`, `Active Energy`.
- Avoid awkward template-generated phrasing like `Top 5 Running by Duration`.

## Metric Formatting

- `Duration`: round to the nearest minute.
- `Distance`: show kilometers with one decimal place when needed.
- `Heart rate`: show whole bpm values.
- `Energy`: show whole kJ values.
- `Comparison deltas`: show signed rounded values, for example `+2 sessions`.
- `Period summaries`: format values with the same unit-aware rounding rules.

## Date Formatting

- Workouts use a localized date and time string in Singapore time.
- Period summaries and comparisons use readable date labels, not ISO dates.
- Dashboard tables and detail panels must use the same formatter family.

## LLM Prompt Rules

- Send compact tool results to the narrator LLM.
- Round numeric values before serialization.
- Remove large geometry payloads such as GPS route coordinates.
- Use compact JSON separators to reduce token count.
- Never send display-only precision that the UI does not need.

## Component Expectations

- `Fallback`: show recovery guidance, not raw machine data.
- `WorkoutCard` and `WorkoutDetail`: use rounded metrics and localized date/time.
- `RankedList`: render rounded values and optional secondary metrics.
- `PeriodSummary` and `Comparison`: use the same rounding helpers as workouts.
- `TrendChart`: format chart labels and tooltips with the same metric rules.

## Enforcement

- Add or update tests whenever a formatting rule changes.
- Prefer shared formatting helpers over ad hoc string interpolation.
- If a new metric appears, add it to the shared formatter before rendering.
