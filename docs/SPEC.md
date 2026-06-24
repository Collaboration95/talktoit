# tti — API Contract & Template Catalog Specification

> The contract between backend LLM tools and frontend template components.
> This is the seam both sides type against. Every `data` shape here must be
> mirrored 1:1 by a Pydantic model (`app/models/`) and a TypeScript interface
> (`src/types/`).
>
> **Canonical source:** This document. Backend models and frontend types are
> derived from it and must stay in lockstep.

---

## 1. Chat Envelope

Every response from `POST /api/chat` is wrapped in this envelope:

```json
{
  "template_id": "workout_card",
  "data": { /* template-specific payload; see §2 */ },
  "narrative": "Here is your last long run — a 21.1 km session on Saturday."
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template_id` | `string` | yes | Which template component to render. One of the catalog IDs in §2. |
| `data` | `object` | yes | Template-specific payload. Shape varies by `template_id`; must validate against the corresponding schema below. |
| `narrative` | `string` | yes | Short natural-language framing from the LLM (1–2 sentences max). Displayed above/beside the rendered template. |

### Error envelope

When the LLM fails to match a question to a template, returns an invalid `template_id`, or the tools return empty data:

```json
{
  "template_id": "fallback",
  "data": {
    "question": "How many dragons have I slayed this week?",
    "table": null,
    "text": "I couldn't find any data matching that question."
  },
  "narrative": ""
}
```

HTTP status: **200** (the chat endpoint itself didn't fail; the answer is "I don't know").
The frontend distinguishes the fallback case by `template_id === "fallback"`, not by HTTP status.

True server errors (tool crashes, uncategorized failures) return **500** with a standard FastAPI error shape:
```json
{
  "detail": "Internal server error"
}
```

---

## 2. Template Catalog

### 2.1 `workout_card` — Single Workout Summary

Displays one workout session with key metrics and an optional GPS route.

```jsonc
{
  "template_id": "workout_card",
  "data": {
    "activity_type": "Running",             // Human-readable workout type
    "date": "2026-06-20T07:30:00+08:00",    // ISO-8601 workout start date/time in user's timezone
    "duration_minutes": 130.5,               // Total duration in minutes
    "avg_heart_rate": 152,                   // bpm; null if no HR data
    "max_heart_rate": 178,                   // bpm; null if no HR data
    "distance_meters": 21100,                // metres; null for non-distance activities
    "distance_unit": "km",                   // "km" or "m" — display unit only; the numeric value is always metres
    "energy_burned_kj": 4500,                // kilojoules; null if not available
    "elevation_ascent_meters": 85,           // total elevation gain; null if not available
    "gps_route": null                        // GeoJSON LineString for GPS track; null if no route
  }
}
```

#### `gps_route` sub-object (only present when a GPS route exists)

```jsonc
{
  "type": "LineString",
  "coordinates": [
    [103.8198, 1.3521],   // [longitude, latitude]
    [103.8204, 1.3532]
  ]
}
```

**Optional-field semantics:** Every field except `template_id`, `activity_type`, and `date`
is **absent or present as its declared type** — never `undefined`. The frontend checks `if
("gps_route" in data)` to decide whether to render the map.

Field | Required | Nullable | Unit
---|---|---|---
`activity_type` | yes | no | —
`date` | yes | no | ISO-8601 with timezone
`duration_minutes` | yes | no | minutes
`avg_heart_rate` | yes | yes | bpm
`max_heart_rate` | yes | yes | bpm
`distance_meters` | yes | yes | metres
`distance_unit` | yes | no | `"km"` or `"m"`
`energy_burned_kj` | yes | yes | kilojoules
`elevation_ascent_meters` | yes | yes | metres
`gps_route` | optional | yes | GeoJSON LineString or null

#### Example payload

```json
{
  "template_id": "workout_card",
  "data": {
    "activity_type": "Running",
    "date": "2026-06-20T07:30:00+08:00",
    "duration_minutes": 130.5,
    "avg_heart_rate": 152,
    "max_heart_rate": 178,
    "distance_meters": 21100,
    "distance_unit": "km",
    "energy_burned_kj": 4500,
    "elevation_ascent_meters": 85,
    "gps_route": null
  },
  "narrative": "Your last long run was a 21.1 km session on Saturday — 2h 10m at an average of 152 bpm."
}
```

---

### 2.2 `ranked_list` — Ordered Rows

Displays an ordered list of items with a primary value, optional secondary metric, and unit.

```jsonc
{
  "template_id": "ranked_list",
  "data": {
    "title": "Top 5 Longest Runs This Year",
    "rows": [
      {
        "rank": 1,
        "label": "21.1 km run — 2026-06-20",
        "value": 21100,
        "unit": "m",
        "secondary_value": 130.5,
        "secondary_unit": "min"
      }
    ]
  }
}
```

#### Row fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `rank` | yes | no | Display rank (1-based) |
| `label` | yes | no | Human-readable description of the item |
| `value` | yes | no | Primary metric value |
| `unit` | yes | no | Unit label for `value` (e.g. "bpm", "m", "km", "min", "kcal") |
| `secondary_value` | optional | no | Second metric (e.g. duration next to distance) |
| `secondary_unit` | optional | no | Unit label for `secondary_value` |

**Optional-field semantics:** `secondary_value` and `secondary_unit` are either both
present or both absent. Never one without the other.

#### Example payload

```json
{
  "template_id": "ranked_list",
  "data": {
    "title": "Top 5 Longest Runs This Year",
    "rows": [
      { "rank": 1, "label": "Jun 20 Half Marathon", "value": 21100, "unit": "m", "secondary_value": 130.5, "secondary_unit": "min" },
      { "rank": 2, "label": "May 15 Long Run",      "value": 18500, "unit": "m", "secondary_value": 115.2, "secondary_unit": "min" },
      { "rank": 3, "label": "Apr 28 — Trail Run",    "value": 16200, "unit": "m", "secondary_value": 140.1, "secondary_unit": "min" },
      { "rank": 4, "label": "Mar 10 — Tempo",        "value": 15000, "unit": "m", "secondary_value": 87.3,  "secondary_unit": "min" },
      { "rank": 5, "label": "Feb 22 — Recovery",     "value": 12000, "unit": "m", "secondary_value": 78.0,  "secondary_unit": "min" }
    ]
  },
  "narrative": "Your five longest runs this year range from 12 km to a half marathon."
}
```

---

### 2.3 `trend_chart` — Metric Over Time

Displays a line/area chart of a single metric bucketed by a time granularity.

```jsonc
{
  "template_id": "trend_chart",
  "data": {
    "title": "Resting Heart Rate — 2026",
    "metric_label": "Resting HR",
    "metric_unit": "bpm",
    "granularity": "week",       // "day" | "week" | "month"
    "series": [
      { "bucket": "2026-W01", "value": 48 },
      { "bucket": "2026-W02", "value": 47 },
      { "bucket": "2026-W03", "value": 49 }
    ]
  }
}
```

#### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `title` | yes | no | Chart heading |
| `metric_label` | yes | no | Axis/legend label |
| `metric_unit` | yes | no | Unit (bpm, kg, km, etc.) |
| `granularity` | yes | no | Bucket size: `"day"`, `"week"`, or `"month"` |
| `series` | yes | no | Ordered list of `(bucket, value)` points |

Each element in `series`:

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `bucket` | yes | no | String label: ISO date (`"2026-06-20"`), ISO week (`"2026-W25"`), or ISO month (`"2026-06"`) depending on `granularity` |
| `value` | yes | yes | Metric value; null when no data exists for that bucket (sparse output) |

**Empty/sparse series:** If the metric is absent from the export, `series` is an empty
array `[]`. Buckets with no data still produce a row with `value: null` so the chart
renders gaps rather than connecting non-existent points.

#### Example payload

```json
{
  "template_id": "trend_chart",
  "data": {
    "title": "Resting Heart Rate This Year",
    "metric_label": "Resting HR",
    "metric_unit": "bpm",
    "granularity": "week",
    "series": [
      { "bucket": "2026-W01", "value": 48 },
      { "bucket": "2026-W02", "value": 47 },
      { "bucket": "2026-W03", "value": null },
      { "bucket": "2026-W04", "value": 49 },
      { "bucket": "2026-W05", "value": 48 },
      { "bucket": "2026-W06", "value": 47 }
    ]
  },
  "narrative": "Your resting heart rate has been steady around 47–49 bpm this year."
}
```

---

### 2.4 `period_summary` — Aggregate Totals

Summarises key metrics for a time period (last week, this month, etc.).

```jsonc
{
  "template_id": "period_summary",
  "data": {
    "title": "Last Week Training Summary",
    "period_start": "2026-06-15",
    "period_end": "2026-06-21",
    "metrics": [
      { "label": "Workouts",     "value": 7,   "unit": "sessions" },
      { "label": "Total Distance", "value": 42.5, "unit": "km" },
      { "label": "Active Energy",  "value": 14500, "unit": "kJ" },
      { "label": "Total Duration", "value": 8.5, "unit": "hours" }
    ]
  }
}
```

#### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `title` | yes | no | Summary heading |
| `period_start` | yes | no | ISO date string (YYYY-MM-DD) |
| `period_end` | yes | no | ISO date string (YYYY-MM-DD) |
| `metrics` | yes | no | List of labelled metrics |

Each metric:

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `label` | yes | no | Human-readable name |
| `value` | yes | yes | Numeric value; null if metric not available |
| `unit` | yes | no | Display unit |

#### Example payload

```json
{
  "template_id": "period_summary",
  "data": {
    "title": "Last Week Training",
    "period_start": "2026-06-15",
    "period_end": "2026-06-21",
    "metrics": [
      { "label": "Workouts",       "value": 7,     "unit": "sessions" },
      { "label": "Total Distance", "value": 42.5,  "unit": "km" },
      { "label": "Active Energy",  "value": 14500, "unit": "kJ" },
      { "label": "Total Duration", "value": 8.5,   "unit": "hours" },
      { "label": "Avg Heart Rate", "value": null,  "unit": "bpm" }
    ]
  },
  "narrative": "You trained 7 times last week, covering 42.5 km and burning 14,500 kJ."
}
```

---

### 2.5 `comparison` — Period vs Period Deltas

Compares two equal-length periods, showing absolute deltas and direction.

```jsonc
{
  "template_id": "comparison",
  "data": {
    "title": "Running: This Month vs Last Month",
    "this_period_label": "Jun 2026",
    "last_period_label": "May 2026",
    "metrics": [
      {
        "label": "Total Distance",
        "this_value": 168,
        "last_value": 152,
        "delta": 16,
        "unit": "km",
        "direction": "up"
      }
    ]
  }
}
```

#### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `title` | yes | no | Comparison heading |
| `this_period_label` | yes | no | Label for the current period (e.g. "Jun 2026") |
| `last_period_label` | yes | no | Label for the previous period (e.g. "May 2026") |
| `metrics` | yes | no | List of compared metrics |

Each metric:

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `label` | yes | no | Metric name |
| `this_value` | yes | yes | Value for current period; null if not available |
| `last_value` | yes | yes | Value for previous period; null if not available |
| `delta` | yes | yes | Difference (this − last); null if either value is null |
| `unit` | yes | no | Display unit |
| `direction` | yes | no | `"up"`, `"down"`, or `"flat"` — visual direction indicator |

#### Example payload

```json
{
  "template_id": "comparison",
  "data": {
    "title": "Running This Month vs Last Month",
    "this_period_label": "Jun 2026",
    "last_period_label": "May 2026",
    "metrics": [
      { "label": "Total Distance", "this_value": 168, "last_value": 152, "delta": 16,  "unit": "km", "direction": "up" },
      { "label": "Total Duration", "this_value": 14.5, "last_value": 13.2, "delta": 1.3, "unit": "hours", "direction": "up" },
      { "label": "Avg Pace",       "this_value": 5.17, "last_value": 5.21, "delta": -0.04, "unit": "min/km", "direction": "down" },
      { "label": "Sessions",       "this_value": 14,  "last_value": 12,  "delta": 2,   "unit": "sessions", "direction": "up" }
    ]
  },
  "narrative": "You ran more this month — 168 km across 14 sessions, up 16 km and 2 sessions from May."
}
```

---

### 2.6 `fallback` — Unmatched / Open-Ended Questions

When no template fits the question, the LLM returns a generic text answer with an
optional simple key-value table.

```jsonc
{
  "template_id": "fallback",
  "data": {
    "question": "What's the best time of day to work out?",
    "table": null,
    "text": "I don't have enough data to answer that specifically. Try asking about your workouts, heart rate, or training volume."
  }
}
```

#### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `question` | yes | no | Echo of the user's question |
| `table` | yes | yes | Optional array of `{ key, value }` rows; null if no structured data |
| `text` | yes | yes | Free-text LLM response; null if only table data |

Each table row:

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `key` | yes | no | Row label |
| `value` | yes | no | Row value (stringified) |

#### Example payload (with table)

```json
{
  "template_id": "fallback",
  "data": {
    "question": "what's the best time to work out",
    "table": [
      { "key": "Tip", "value": "Morning workouts tend to have higher consistency" },
      { "key": "Data", "value": "Most of your runs start between 6–8 AM" }
    ],
    "text": "Based on your habits, you prefer morning sessions. Research suggests consistency matters more than time of day."
  },
  "narrative": ""
}
```

---

## 3. API Surface

### `POST /api/chat`

**Request:**

```json
{
  "question": "Show me my last long run"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | `string` | yes | Natural-language question from the user. No length limit enforced by the API (frontend may cap displayed input). |

**Response:** `200` with the envelope (§1).

**Error responses:**

| Status | Body | Cause |
|--------|------|-------|
| 422 | `{ "detail": [{ "loc": ["body", "question"], ... }] }` | Missing or invalid request body |
| 500 | `{ "detail": "Internal server error" }` | Tool crash, DB error, unhandled exception |

### `GET /health`

Returns `{"status": "ok"}`. Used by the frontend to verify backend connectivity
before sending chat requests.

### Dashboard endpoints (sketch — finalized in Phase 7)

These are documented here for the dashboard pane layout; shapes are provisional:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/dashboard/summary` | Activity rings/energy for a date range |
| `GET` | `/api/dashboard/workouts` | Workout list for a date range |
| `GET` | `/api/dashboard/workouts/{id}` | Single workout detail (incl. GPS) |
| `GET` | `/api/dashboard/steps` | Steps/distance trend |
| `GET` | `/api/dashboard/heart` | Resting HR & HRV trend |
| `GET` | `/api/dashboard/sleep` | Sleep duration trend |
| `GET` | `/api/dashboard/capabilities` | Which data sources are present in this export |

Query params for trend endpoints: `granularity=day|week|month`, `start`, `end`.

---

## 4. Privacy Invariant

**Raw rows never reach the LLM.** The LLM operates exclusively through tools — each
tool returns a structured, pre-aggregated result. Only the **small slice** needed to
pick a template and compose framing text is surfaced to the model.

### Per-tool LLM-visible slice

| Tool | What the LLM sees |
|------|-------------------|
| `get_last_workout(activity_type)` | Activity type, date, duration, avg/max HR, distance, elevation — the same fields that populate `workout_card.data`. **Not** raw record rows. |
| `get_top_workouts(activity_type, metric, n, period)` | List of `{ label, value, unit, secondary_value?, secondary_unit? }` — the rows for `ranked_list.data`. **Not** raw workout/statistics rows. |
| `get_trend(metric_id, granularity, period)` | Series of `(bucket, value)` points. **Not** raw record rows. |
| `get_period_summary(period)` | Aggregate numbers (workout count, total distance, energy, duration). **Not** raw rows. |
| `get_comparison(metric_id, this_period, last_period)` | Pairs of `(this_value, last_value, delta, direction)`. **Not** raw rows. |
| `get_fallback_answer(question)` | No data — just the question text. |

The LLM **never** sees `source_name`, `device`, `creation_date`, `MetadataEntry`
values, HRV beat lists, or any record-level data. The bulk of data flows tool →
frontend template, entirely bypassing the model.

---

## 5. Type Authorship

- **Canonical form:** This document (SPEC.md).
- **Backend types:** Pydantic models in `app/models/` — each template's `data` gets
  a model class named after the `template_id` (e.g. `WorkoutCardData`, `RankedListData`).
- **Frontend types:** TypeScript interfaces in `src/types/` — mirror the Pydantic
  shapes exactly, authored to satisfy `exactOptionalPropertyTypes` and
  `noUncheckedIndexedAccess`.
- **Synchronisation:** When SPEC.md changes, both models and interfaces must be
  updated in the same PR. The `make typecheck` (Pyright + tsc) gates will catch
  mismatches.

---

*Created: 2026-06-24. Derives template catalog from DISCOVERY §2 and §3.
The `data` schemas are the source of truth for Pydantic models and TS interfaces.
Sign-off: pending.*
