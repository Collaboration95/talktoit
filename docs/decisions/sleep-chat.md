# Decision: sleep chat measurements

**Status:** Accepted for implementation in TTI-A-002 (#193)
**Scope:** Reuse the dashboard's measured sleep trend in chat. This decision does not
define sleep quality, a target, or a medical interpretation.

## Current behavior at baseline `49510a7`

`GET /api/dashboard/sleep` and `/sleep/stages` both read
`HKCategoryTypeIdentifierSleepAnalysis` rows with `source_name != 'AutoSleep'`.
The SQL predicate also excludes a NULL source name. Both use Asia/Singapore local
calendar dates and a half-open UTC query window derived from the requested inclusive
local dates. Rows are selected by `start_date`; a row that starts outside the window
is excluded even if its interval overlaps it.

The sleep trend unions **all returned category intervals**, without inspecting the
category label. That includes asleep, awake, and in-bed rows. It buckets each entire
interval by its local start date (then the requested day/week/month bucket), unions
overlapping or touching intervals within that bucket, and reports elapsed hours. An
overnight interval is therefore attributed wholly to the bucket containing its start;
it is not split at midnight or at a week/month boundary, and it is not clipped to the
requested window end.

The stage endpoint instead totals only labels containing `Asleep`, including a
stage-less `Asleep` observation. It unions asleep intervals for `total_asleep_hours`.
Recognized Core, Deep, and REM labels are unioned separately; the stage partition is
hidden if its sum exceeds the asleep union. Awake and InBed intervals do not count
toward that total. As a result, these totals can differ even with the same rows and
source filter: the sleep trend is measured category-interval coverage, while the
stage endpoint is measured asleep time.

Synthetic oracle: an InBed interval 21:30–00:00 containing Core sleep 22:00–23:00 and
Awake 23:00–23:30 gives a 2.5-hour daily trend and a 1-hour asleep total/Core stage.
The regression test is `backend/tests/unit/test_sleep_stages.py::test_sleep_trend_includes_awake_and_in_bed_intervals_but_stages_do_not`.

Missingness is represented by a null trend point when no matching rows start in that
bucket. Zero is not synthesized for an empty day. A present interval may have zero
duration in malformed data; do not turn missing rows into a measured zero.

## Decision

Keep the existing dashboard result unchanged and make chat share its exact sleep
trend calculation. This preserves user-visible behavior and keeps totals consistent
between dashboard and chat. Do not rename it “time asleep”: it includes Awake and
InBed observations and can exceed asleep time. The stages endpoint remains the
source for asleep-only totals and stages.

Use Asia/Singapore as the date and bucket timezone, inclusive local date arguments,
and the existing start-date selection / start-bucket attribution / full-interval
union rules above. Exclude the exact `AutoSleep` source and preserve current NULL
source behavior. Do not choose one source among other devices or de-duplicate
overlapping sources; interval union already avoids time double counting.

If no rows occur in a bucket, emit `value: null`, not zero. If rows exist but have no
usable positive interval duration, retain the current measured-data semantics and
make no inference of sleep or wakefulness. Keep all values local: neither sleep
questions nor sleep results may be sent to a remote planner, tool provider, or
narrative model. Use the deterministic local planner and local renderer for supported
sleep requests; unsupported wording should follow the app's normal clarification or
fallback path without remote health-data egress.

## Minimal implementation contract

1. Move the shared local interval query/aggregation into `backend/app/db/queries.py`
   (or a private helper called by it). Have both dashboard sleep and chat call this
   implementation; leave the `/sleep` and `/sleep/stages` response contracts intact.
2. Add a validated `sleep_trend` registry query with `start`, `end`, and
   `granularity: day | week | month`. Keep it separate from numeric `metric_trend`,
   because catalog sleep is categorical and uses interval union rather than numeric
   row aggregation.
3. Add a dedicated validated chat tool/dispatcher for this query. Return the existing
   `trend_chart` payload (`metric_label: Sleep`, `metric_unit: hours`, bucket/value
   series) so the existing template can render it. Do not add a new template type.
4. Add deterministic local planning for clear sleep-trend requests. Anchor relative
   windows to the imported dataset's latest date, not the computer clock. For an
   absent or ambiguous date range, use the existing clarification/fallback behavior;
   do not send the question to a hosted planner.
5. Test exact dashboard/chat parity over overlapping asleep, awake and in-bed rows,
   AutoSleep exclusion, an overnight interval, each supported granularity, and null
   buckets. Include a stage-less Asleep row and keep the sleep calculation local.

No schema migration, new sleep sensors, total-asleep reinterpretation, sleep score,
or medical claim is part of this work.
