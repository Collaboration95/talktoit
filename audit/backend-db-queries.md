# Database, queries, and analytics registry (QRY-*)

Scope: `backend/app/db/` (schema, connection, aggregations, data profile,
dashboard cache, query functions) and `backend/app/analytics/` (metric catalog,
query registry). The numeric findings here are the ones a user will notice as
wrong totals on the dashboard and in chat answers.

---

## QRY-1 — duration totals sum mixed units without converting

**High** — `backend/app/db/queries.py:192` and `:222`
(consumers at `:694-719` and `:750-768`)

```sql
SELECT COUNT(*) AS cnt, SUM(duration) AS dur FROM workouts WHERE …
SELECT COUNT(*) AS cnt, SUM(w.duration) AS dur FROM workouts w WHERE …
```

`workouts.duration` is stored next to `workouts.duration_unit`, and the
columns are never consulted. A workout recorded as `1.0 hr` contributes
`1.0` to a total that the UI labels `min` (`queries.py:719`). Both
`get_period_summary` and the comparison path (`_period_stats`) use these
statements, so the "Total Duration" tile and every period comparison inherit the
error.

**Evidence.**

```
$ ./backend/.venv/bin/python audit/repro/tti_units.py
# one 1.0 hr workout + one 60.0 min workout = 120 minutes
period_summary: Workouts = 2.0 sessions
period_summary: Total Duration = 61.0 min     <-- should be 120
```

The rest of the codebase does normalize: `minutes_from_duration`
(`backend/app/db/aggregations.py:238-254`) converts `hr` to minutes and is
used by the ranked-workout and training-volume paths
(`queries.py:366`, `:454`, `:567`). That is what makes this a bug rather
than a convention: the same workout shows a correct duration in the workout list
and a wrong one in the period summary.

**Impact.** Any period containing an `hr`-unit workout under-reports total
duration by a factor of 60, and comparisons between periods mix units on both
sides. Ranked lists that order by duration stay correct (they convert per row),
so two panels can disagree about the same data.

**Fix.** Aggregate per unit: either convert inside SQL
(`SUM(CASE WHEN duration_unit = 'hr' THEN duration * 60.0 ELSE duration END)`)
or drop the aggregate and reuse `minutes_from_duration` per row in Python as the
other paths already do. While touching it, note that `minutes_from_duration`
passes any unit other than `hr` through unchanged, so `sec` would be counted
as minutes; make the helper explicit about the units it accepts.

---

## QRY-2 — active energy is summed across rows whose units are never checked

**Medium** — `queries.py:211-219` and `:241-249`; output labelled `kJ` at
`:720`

```sql
SELECT SUM(ws.sum) FROM workout_statistics ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.type = 'HKQuantityTypeIdentifierActiveEnergyBurned' AND …
```

The statement filters on the statistic's type but ignores `ws.unit`, and the
result is reported as kJ. Apple Health records `ActiveEnergyBurned` in either
`kJ` or `kcal` depending on device and locale; the fixture uses `kJ`
(`backend/tests/fixtures/sample.xml:180`). One `kcal` row therefore
contributes a number that is off by 4.184x and is added to kJ rows as if the
units matched. `docs/HEALTH_DATA_UI_STYLEGUIDE.md` states the intended
presentation ("Energy: show whole kJ values"), which the query cannot honour
without a conversion.

**Impact.** Period summaries and comparisons report an energy total that is
wrong by a constant factor when the export used kcal, and meaningless when it
mixes both. Because the number is plausible, the user has no way to notice.

**Fix.** Normalize in SQL as the distance query does
(`CASE WHEN LOWER(ws.unit) = 'kcal' THEN ws.sum * 4.184 ELSE ws.sum END`), and
decide explicitly what an unknown unit should do. Add a mixed-unit fixture test
(TST-5).

---

## QRY-3 — the distance conversion is duplicated six times and silently treats unknown units as metres

**Low (correctness risk, maintainability)** — `queries.py:73-76`, `:115-118`,
`:159-162`, `:198-201`, `:228-231`, `:258-261`

The same `CASE` expression — `km → * 1000`, `mi|mile|miles → * 1609.344`,
`ELSE sum` — is copy-pasted into six statements covering the summary, top
workouts, workout collection, period summary, period summary filtered, and
training volume paths. The `ELSE` arm assumes metres, so a unit of `yd`,
`ft`, or anything Apple adds later is silently treated as metres.

**Impact.** No user-visible defect today (the common units are handled), but six
copies means six places to fix, and one of them will be missed. The duration side
of the same file has a single shared helper, so the inconsistency is within one
module.

**Fix.** Extract a `distance_to_metres_sql(column)` fragment or a Python helper
next to `minutes_from_duration`, and make unknown units raise or be counted so
the silence is at least visible.

---

## QRY-4 — "all time" is expressed with hardcoded 1970 and 2100 sentinels

**Low** — `queries.py:537-539`

```python
if start is None or end is None:
    utc_start = datetime(1970, 1, 1)
    utc_end = datetime(2100, 1, 1)
```

Two magic dates stand in for "no bound". They work, but the codebase reads the
dataset's own date range everywhere else (`data_profile.latest_date`,
`AGENTS.md`'s rule about using the dataset's latest date rather than the clock),
so a future dataset dated after 2099 would silently be truncated, and a review of
"which timezone are these in" cannot be answered from the code.

**Fix.** Use `None`-aware SQL (`(? IS NULL OR start_date >= ?)`) or derive the
bounds from the profile, and name the constants if they stay.

---

## QRY-5 — period-summary titles use ISO dates while every other label is human

**Low (presentation inconsistency)** — `queries.py:712-714`

```python
auto_title = title or f"Training Summary: {period_start.isoformat()} to {period_end.isoformat()}"
```

The chart title renders as `Training Summary: 2026-06-01 to 2026-06-30`, while
comparison labels use month names (`local_planner.py:42`, `:65-66`) and the
frontend formats dates through `formatDateRange`. The styleguide asks for
specific, short labels; an ISO range is the one place the backend hands the UI
pre-formatted technical text.

**Fix.** Build the title from the same label vocabulary the comparison path uses
(`June 2026`), or leave the title empty and let the renderer format the range it
already receives.

---

## QRY-6 — one query is assembled with `.format()` in a module that documents avoiding it

**Low** — `queries.py:543-547`

`_SQL_TOP_WORKOUTS` is a template whose `order_col` placeholder is filled with a
value from `_TOP_WORKOUTS_ORDER_COLUMNS`, a fixed literal whitelist, so there is
no injection path today. The module's own guidance is that query text is static
SQL with bound parameters, and this statement is the exception: the ordering
column is interpolated text, and a future caller-indexed mapping would turn a
lookup miss into a `KeyError` or an arbitrary column name.

**Fix.** Inline the three variants as separate statements, or assert the ordering
against the whitelist and document why interpolation is safe here.

---

## QRY-7 — an unknown metric id produces an empty chart instead of a rejection

**Low (validation gap, dead validator)** — `backend/app/analytics/registry.py:110`
and `:292-303`; rendering path `backend/app/db/queries.py:636-669`

`MetricTrendInput.metric_id` is a bare `str`, so nothing checks it against
`METRIC_CATALOG` before `execute_metric_trend` reaches `get_trend`. An
unknown identifier matches no rows, `METRIC_META.get(metric_id, (metric_id,
""))` falls back to the raw identifier, and the user gets an empty series titled
with an Apple Health constant such as
`HKQuantityTypeIdentifierHeartRateVaribility`. Meanwhile
`validate_query_catalogue()`, which exists to reject exactly this class of
declaration error, has no runtime caller at all: the only call site is
`backend/tests/unit/test_query_registry.py:42`.

**Impact.** A typo or a locale-specific metric name degrades to a blank chart
with a technical label rather than a clear "unsupported metric" answer, and the
registry's declared guarantees are enforced only in CI, never in the process that
serves users.

**Fix.** Type `metric_id` against the catalog (a `Literal` built from
`METRIC_CATALOG`, or an explicit membership check that raises), and call
`validate_query_catalogue()` once during application startup next to the other
migrations so a broken registry fails loudly at boot.
