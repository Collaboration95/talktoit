# tti v1 API and template contract

This document is the durable contract between the local backend analytics layer and the
frontend renderers. Backend query code may evolve internally, but a response that claims a
known `template_id` must continue to satisfy the corresponding payload below.

## 1. Chat envelope

Every successful chat response has this JSON shape:

```json
{
  "template_id": "workout_card",
  "data": {},
  "narrative": "Short factual context.",
  "metadata": {
    "api_version": "v1",
    "provenance": "deterministic_local",
    "dataset_version_id": "ds_…",
    "coverage_start": "2026-01-01",
    "coverage_end": "2026-06-10",
    "generated_at": "2026-07-21T10:00:00+00:00"
  }
}
```

`template_id` selects the renderer. `data` is validated server-side before it is returned.
Known payloads use the models in `backend/app/models/templates.py`; unknown template IDs must
be rendered by the frontend fallback path and must not crash the chat view.

`metadata.provenance` is one of `unknown`, `deterministic_local`, `remote_planned`, `fallback`,
or `cached`. Dataset and coverage fields are nullable when no validated import is active.
Dates are ISO-8601 strings. Numeric values are measured or explicitly derived facts; the
contract does not authorize diagnostic or causal language.

## 2. Known template payloads

### 2.1 `workout_card`

```json
{
  "activity_type": "Running",
  "date": "2026-06-05T07:00:00+08:00",
  "duration_minutes": 45.5,
  "avg_heart_rate": 148,
  "max_heart_rate": 171,
  "distance_meters": 8500,
  "distance_unit": "m",
  "energy_burned_kj": 2500,
  "elevation_ascent_meters": 45.2,
  "gps_route": {"type": "LineString", "coordinates": [[103.8, 1.3]]},
  "workout_id": 1,
  "workout_fingerprint": "0123456789abcdef"
}
```

Required fields are `activity_type`, `date`, `duration_minutes`, `avg_heart_rate`,
`max_heart_rate`, `distance_meters`, `distance_unit`, `energy_burned_kj`, and
`elevation_ascent_meters`. Optional fields may be absent or explicitly `null`; the frontend
must treat both as “not available”. GPS coordinates remain local and must never enter provider
or narrative payloads.

### 2.2 `ranked_list`

```json
{
  "title": "Top running workouts by distance",
  "rows": [
    {"rank": 1, "label": "2026-06-05", "value": 8.5, "unit": "km"}
  ]
}
```

Each row requires `rank`, `label`, `value`, and `unit`. `secondary_value` and `secondary_unit`
are optional and should be omitted when not measured.

### 2.3 `trend_chart`

```json
{
  "title": "Resting heart rate",
  "metric_label": "Resting HR",
  "metric_unit": "bpm",
  "granularity": "week",
  "series": [{"bucket": "2026-W23", "value": 51}]
}
```

`granularity` is `day`, `week`, or `month`. A missing bucket is represented by `value: null`,
not zero.

### 2.4 `period_summary`

```json
{
  "title": "Training summary",
  "period_start": "2026-06-01",
  "period_end": "2026-06-10",
  "metrics": [{"label": "Workouts", "value": 4, "unit": "sessions"}]
}
```

### 2.5 `comparison`

```json
{
  "title": "This period vs last period",
  "this_period_label": "June 1–10",
  "last_period_label": "May 22–31",
  "metrics": [
    {"label": "Distance", "this_value": 25, "last_value": 20,
     "delta": 5, "unit": "km", "direction": "up"}
  ]
}
```

`direction` is `up`, `down`, or `flat` and describes the displayed numeric comparison only.
It is not a health interpretation.

### 2.6 `fallback`

```json
{
  "question": "The original user question",
  "table": [{"key": "coverage", "value": "2026-01-01 to 2026-06-10"}],
  "text": "A concise, safe explanation."
}
```

`table` and `text` are independently nullable. Fallbacks must be useful without exposing raw
prompts, SQL, implementation details, or unapproved health records.

## 3. Runtime and compatibility rules

- Trim and bound user questions before database or provider work.
- Resolve relative dates against the active dataset’s latest date, never the computer clock.
- Preserve the `ChatResponse` envelope and validate every known template end to end.
- Unknown templates use the fallback renderer and are treated as compatibility events.
- Error responses use the versioned `ProblemDetail` envelope with a safe error code and request
  ID; they do not include provider exceptions, SQL, paths, prompts, or raw health data.
- Provider egress is controlled by `TTI_PROVIDER_MODE`: `local_only`, `remote_planning`, or
  `remote_planning_and_narration`. Raw records, GPS geometry, device blobs, and source paths
  are never allowed in provider messages.

The Pydantic models and TypeScript types are the executable form of this document. Contract
changes require tests on both sides and an explicit API version decision.
