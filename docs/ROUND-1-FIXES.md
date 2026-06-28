# tti — Round-1 Fixes: Leftover Requirements & Remediation Spec

> Canonical source for everything that was deferred, drifted, or left incomplete
> after the initial 8-phase build. This document records the gap, the target
> state, concrete implementation requirements, and objective acceptance criteria.
>
> Derived from the full project review conducted 2026-06-27.
> Each issue is tagged with the original phase it traces back to.

---

## Issue Map

```
┌───────┬──────────────────────────────────────────────────────────────────┬──────────┬──────────┐
│  ID   │                             Title                                │ Severity │  Origin  │
├───────┼──────────────────────────────────────────────────────────────────┼──────────┼──────────┤
│ R1-01 │ Workout detail endpoint + frontend detail view                   │ 🔴 HIGH  │ Phase 7  │
│ R1-02 │ Pyright config ↔ ENGINEERING.md alignment                        │ 🟡 MED   │ Phase 0  │
│ R1-03 │ gps_route absent-vs-null serialization hardening                 │ 🟡 MED   │ Phase 1/5│
│ R1-04 │ Dashboard rings panel: table → Tremor gauge upgrade              │ 🟡 MED   │ Phase 7  │
│ R1-05 │ Empty store/ directory cleanup                                   │ 🟡 MED   │ Phase 0  │
│ R1-06 │ Peak-RSS ingestion assertion (manual verification)               │ 🟡 MED   │ Phase 2  │
│ R1-07 │ Makefile install target docs alignment                           │ 🟢 LOW   │ Phase 0  │
│ R1-08 │ package.json allowScripts documentation                          │ 🟢 LOW   │ Phase 0  │
│ R1-09 │ Dashboard workout-list → detail navigation UX                    │ 🟡 MED   │ Phase 7  │
│ R1-10 │ Per-module coverage enforcement (ingest ≥90%, llm ≥70%)         │ 🟡 MED   │ Phase 0  │
│ R1-11 │ ChatResponse.data typing (Any → discriminated union)            │ 🟡 MED   │ Phase 4  │
│ R1-12 │ Frontend health-check before first chat request                  │ 🟢 LOW   │ Phase 6  │
└───────┴──────────────────────────────────────────────────────────────────┴──────────┴──────────┘
```

---

## R1-01 — Workout Detail Endpoint & Frontend Detail View

**Severity:** 🔴 HIGH — functional gap
**Origin:** Phase 7 (Dashboard)
**Source:** `docs/SPEC.md` §3 lists `GET /api/dashboard/workouts/{id}`; neither backend nor frontend implements it.

### Current state

- `GET /api/dashboard/workouts` returns a flat list of `WorkoutSummary` objects.
- The dashboard renders a flat HTML table with no clickable rows.
- There is no way to see a single workout's full detail (all metrics, GPS map).

### Target state

A user clicks a workout row in the dashboard → sees a detail panel with:
- All numeric metrics (duration, avg/max HR, distance, energy, elevation).
- A GPS route map **when a route exists** (gracefully hidden otherwise).
- The inline-sourced metadata (brand, weather, etc.).

### Backend requirements

#### `GET /api/dashboard/workouts/{id}`

**Response shape:**

```jsonc
{
  "id": 42,
  "activity_type": "Running",
  "date": "2026-06-20T07:30:00+08:00",      // ISO-8601 local timezone
  "duration_minutes": 130.5,
  "avg_heart_rate": 152,
  "max_heart_rate": 178,
  "distance_meters": 21100,
  "distance_unit": "km",
  "energy_burned_kj": 4500,
  "elevation_ascent_meters": 85,
  "source_name": "Apple Watch",
  "gps_route": {                               // null when no route exists
    "type": "LineString",
    "coordinates": [[103.8198, 1.3521], [103.8204, 1.3532]]
  },
  "metadata": [                                 // empty array when no metadata
    { "key": "HKWeatherTemperature", "value": "28 °C" },
    { "key": "HKWorkoutBrandName", "value": "Apple Watch" }
  ]
}
```

**Fields:**

| Field | Type | Required | Nullable | Notes |
|-------|------|----------|----------|-------|
| `id` | `int` | yes | no | DB primary key |
| `activity_type` | `string` | yes | no | |
| `date` | `string` | yes | no | ISO-8601 with timezone, local time |
| `duration_minutes` | `float` | yes | yes | |
| `avg_heart_rate` | `int` | yes | yes | Rounded from float |
| `max_heart_rate` | `int` | yes | yes | |
| `distance_meters` | `float` | yes | yes | |
| `distance_unit` | `"km"` \| `"m"` | yes | no | Hard-coded `"km"` for consistency with workout_card |
| `energy_burned_kj` | `float` | yes | yes | |
| `elevation_ascent_meters` | `float` | yes | yes | |
| `source_name` | `string` | yes | no | |
| `gps_route` | `GpsRoute` \| `null` | yes | yes | GeoJSON LineString; `null` when no route |
| `metadata` | `array` | yes | no | Array of `{key, value}`; empty `[]` when none |

**Error cases:**

| Status | Body | Condition |
|--------|------|-----------|
| 200 | (above payload) | Workout found |
| 404 | `{ "detail": "Workout not found" }` | `id` does not exist |

**Pydantic model** (in `app/models/dashboard.py`):

```python
class WorkoutDetail(BaseModel):
    """Full detail for a single workout."""
    id: int
    activity_type: str
    date: str  # ISO-8601 local
    duration_minutes: float | None
    avg_heart_rate: int | None
    max_heart_rate: int | None
    distance_meters: float | None
    distance_unit: Literal["km", "m"]
    energy_burned_kj: float | None
    elevation_ascent_meters: float | None
    source_name: str
    gps_route: GpsRoute | None  # None → omitted in JSON via exclude_none
    metadata: list[KeyValuePair]

class KeyValuePair(BaseModel):
    key: str
    value: str
```

**Implementation note:** The GPS route must be loaded from the `workout_routes` file path stored during ingestion. For v1, if the GPX file referenced by `FileReference/path` exists on disk, parse it into the GeoJSON `LineString`. If the file is missing or parsing fails, return `null`. GPX parsing is isolated in a pure helper so it can be unit-tested. Use `lxml` for GPX parsing (already a dependency).

#### SQL additions

```sql
-- Fetch single workout with all joined data
SELECT w.id, w.activity_type, w.start_date, w.duration, w.duration_unit,
       w.source_name,
       hr.average AS avg_hr, hr.maximum AS max_hr,
       dist.sum AS distance_m, energy.sum AS energy_kj,
       TRY_CAST(elev.value AS DOUBLE) AS elevation_m
FROM workouts w
LEFT JOIN workout_statistics hr ON ... AND hr.type = 'HKQuantityTypeIdentifierHeartRate'
LEFT JOIN ( ... distance join ... ) dist ON ...
LEFT JOIN workout_statistics energy ON ... AND energy.type = 'HKQuantityTypeIdentifierActiveEnergyBurned'
LEFT JOIN workout_metadata elev ON ... AND elev.key = 'HKElevationAscended'
WHERE w.id = ?

-- Fetch metadata for a workout
SELECT key, value FROM workout_metadata WHERE workout_id = ?

-- Fetch route file path
SELECT file_path FROM workout_routes WHERE workout_id = ?
```

### Frontend requirements

#### Workout detail panel component

New file: `frontend/src/components/workout-detail.tsx`

- Receives `workoutId: number` as prop.
- Fetches `GET /api/dashboard/workouts/{id}` on mount.
- Renders a card with all metrics (same grid layout as `WorkoutCard`).
- Renders a GPS map **only when** `gps_route` is non-null. Use a lightweight map component (Leaflet via `react-leaflet` or a simple ECharts scatter on a blank canvas — ECharts is preferred since it's already in the stack).
- Shows metadata as a key-value table.
- Shows loading/error states.
- Includes a "Back to list" button/link.

#### Dashboard workout list changes

- Each row in the workout table becomes clickable (cursor pointer, hover highlight).
- Click dispatches to show the `WorkoutDetail` panel.
- Navigation uses React state (no URL routing needed for v1).

### Acceptance criteria

- ☐ `GET /api/dashboard/workouts/1` returns the full detail payload with known fixture values (assert exact: duration, avg HR, distance, elevation, source name).
- ☐ `GET /api/dashboard/workouts/999` returns 404.
- ☐ When the fixture workout has a route file path, the response includes `gps_route` with coordinates (mock GPX parsing in test if the file doesn't exist on disk). When a workout has no route, `gps_route` is `null`.
- ☐ Metadata array is non-empty for the Strava-imported workout (fixture: Cycling has `HKWorkoutBrandName: Strava`) and empty for workouts with no metadata.
- ☐ Frontend test: Clicking a workout row shows the detail panel with all fields rendered.
- ☐ Frontend test: A workout with `gps_route: null` renders no map (no crash, no empty map div).
- ☐ Frontend test: Detail panel shows a loading state during fetch and an error state on 404.
- ☐ Backend + frontend quality gates pass (Pyright, tsc, pytest, Vitest, coverage).

### Out of scope

- Real GPX file parsing on disk (mock for tests; real parsing verified manually).
- Fancy map interactions (zoom, pan) — a static rendered route is sufficient.
- URL-based routing (React Router) — simple state toggle for v1.

---

## R1-02 — Pyright Config ↔ ENGINEERING.md Alignment

**Severity:** 🟡 MED — drift between code and docs
**Origin:** Phase 0

### Current state

`backend/pyrightconfig.json` contains 5 relaxed strict-mode rules:

```json
{
  "reportUnknownMemberType": false,
  "reportUnknownVariableType": false,
  "reportUnknownArgumentType": false,    // ← not in ENGINEERING.md
  "reportUnusedFunction": false,         // ← not in ENGINEERING.md
  "reportInvalidTypeForm": false         // ← not in ENGINEERING.md
}
```

`docs/ENGINEERING.md` §2.3 only documents the first two and explicitly says:

> `reportUnknownMemberType` and `reportUnknownVariableType` are relaxed because third-party
> libraries (DuckDB, lxml) ship incomplete stubs … **Revisit and re-enable both** once
> `types-`/stub packages are added for the offending libraries.

### Target state

One of two outcomes (choose and implement):

**Option A — Tighten config (preferred).** Remove the three undocumented relaxations. Fix any resulting type errors by adding `type: ignore` comments or stub improvements. This brings the config into alignment with ENGINEERING.md.

**Option B — Document the drift.** Update ENGINEERING.md §2.3 to explicitly list all 5 relaxed rules with rationale for each. The config becomes the truth; the docs catch up.

Either way, the config and the docs must agree. The current situation where config has 3 extra relaxations with no documented rationale is a correctness risk.

### Acceptance criteria

- ☐ `pyrightconfig.json` and ENGINEERING.md §2.3 agree on the exact set of relaxed strict-mode rules.
- ☐ If Option A was chosen: `uv run --directory backend pyright` exits 0 with no new suppressions needed beyond what's already in the codebase.
- ☐ If Option B was chosen: Every relaxed rule in the config has a sentence in ENGINEERING.md explaining why it's relaxed.
- ☐ The "Open Questions" item #10 in ENGINEERING.md §9 is updated to reflect the final state.

---

## R1-03 — gps_route Absent-vs-Null Serialization Hardening

**Severity:** 🟡 MED — latent fragility
**Origin:** Phases 1 & 5

### Current state

The SPEC §2.1 defines `gps_route` as optional (may be absent entirely). The frontend checks for GPS existence with `"gps_route" in data`. The backend Pydantic model uses `GpsRoute | None = None` and serializes with `model_dump(mode="json", exclude_none=True)`, which omits `gps_route` from the JSON when it's `None`. This works today, but:

- If serialization strategy changes (e.g., `exclude_unset=True` or removing `exclude_none`), `"gps_route": null` would appear in JSON.
- `"gps_route" in data` would then be `true` even though GPS is absent, causing the frontend to render a broken map slot.
- There is no test that asserts the *absence* of `gps_route` in the JSON payload when no GPS exists.

### Target state

1. **Backend test:** Assert that when `gps_route` is `None`, the key is absent from the serialized JSON (not present-as-null).
2. **Frontend test:** Assert that when `gps_route` is absent from the payload, the GPS section is not rendered.
3. **Frontend test:** Assert that when `"gps_route": null` *is* received (defensive), the GPS section is also not rendered (treat null same as absent).

### Acceptance criteria

- ☐ Backend integration test: `get_last_workout` for a workout without a route returns JSON without `"gps_route"` key (use Python `assert "gps_route" not in data_dict`).
- ☐ Frontend Vitest test: `WorkoutCard` rendered with `{ ...data }` (no `gps_route` key) does not contain GPS route text/element.
- ☐ Frontend Vitest test: `WorkoutCard` rendered with `{ ...data, gps_route: null }` also does not render GPS (defensive check).
- ☐ Both tests pass and coverage gates hold.

---

## R1-04 — Dashboard Rings Panel: Table → Tremor Gauge Upgrade

**Severity:** 🟡 MED — UX quality
**Origin:** Phase 7

### Current state

The Activity Rings panel on the dashboard renders a plain HTML `<table>` with energy/exercise/stand numbers. DISCOVERY.md §6 explicitly chose **Tremor** for "Activity Rings / Gauge" as one of the two primary use cases for keeping Tremor in the stack. The current implementation does not use Tremor for this.

### Target state

Replace the `<table>` rendering with a Tremor-based **concentric ring/donut gauge** showing:
- Energy ring (red/pink) — `energy_kj` / `energy_goal_kj`
- Exercise ring (green) — `exercise_min` / `exercise_goal_min`
- Stand ring (blue) — `stand_hours` / `stand_goal_hours`

The Tremor `ProgressCircle` or `DonutChart` component should be used. For v1, show the most recent day's rings prominently and optionally show the last 7 days as a smaller row.

If Tremor v3 does not have a built-in concentric-ring component, fall back to **Chart.js concentric doughnut** (which was the close-second pick per DISCOVERY §6) wrapped in a thin `GaugeChart` wrapper in `frontend/src/charts/`.

**Graceful degradation:** When ring data is absent (no ActivitySummary in the export), hide the entire rings panel (already handled by capabilities probe).

### Acceptance criteria

- ☐ The dashboard "Activity Rings" section renders concentric ring/donut gauges instead of an HTML table.
- ☐ Each of the 3 rings (energy, exercise, stand) is visually distinct and shows current/goal values.
- ☐ When all ring values for the most recent day are 0 or null, rings render at 0% (not crashed, not infinite).
- ☐ The rings panel is hidden when `capabilities` reports no activity summaries.
- ☐ A Vitest snapshot or assertion test verifies the gauges render with known fixture data (at least that the component mounts without error).
- ☐ Frontend typecheck + lint pass.

---

## R1-05 — Empty `store/` Directory Cleanup

**Severity:** 🟡 MED — repo hygiene
**Origin:** Phase 0 (scaffolding)

### Current state

`frontend/src/store/` is an empty directory. ENGINEERING.md §1 lists it as:

> `frontend/src/store/` — Client state (React context or Zustand — TBD)

### Target state

**Remove the empty directory.** The chat view uses `useState` with a discriminated union; the dashboard uses `useState` + `useEffect`. No shared state store is needed for v1. If one is added later, recreate the directory at that time.

### Acceptance criteria

- ☐ `frontend/src/store/` no longer exists in the repo.
- ☐ `git status` shows the deletion cleanly.
- ☐ `make typecheck && make lint && make test` all pass (nothing imports from store/).

---

## R1-06 — Peak-RSS Ingestion Assertion

**Severity:** 🟡 MED — unverified acceptance criterion
**Origin:** Phase 2

### Current state

PHASES.md Phase 2 acceptance criterion:

> ☐ Peak RSS while ingesting a multi-hundred-MB export stays bounded (well under the export size)
> — verified manually and noted

This was never verified. The `lxml.iterparse` approach with `elem.clear()` + parent removal is correct, so peak RSS should be bounded, but there's no evidence.

### Target state

Run a one-time manual verification:

```bash
# macOS
/usr/bin/time -l make ingest EXPORT_PATH=personal-assets/test-data/export_last6mo.xml 2>&1 | grep "maximum resident"

# Or use a simple wrapper script
```

Record the result in a comment in `backend/app/ingest/parser.py` or a note in `docs/ROUND-1-FIXES.md`. The peak RSS should be **< 500 MB** for the 597 MB test export (the file is streamed, never fully loaded). If it's higher, investigate and fix.

### Acceptance criteria

- ☐ A one-line comment is added at the top of `backend/app/ingest/parser.py` with the measured peak RSS for the 597 MB test export.
- ☐ If peak RSS exceeds 1 GB for the 597 MB file, an investigation issue is filed (the streaming approach should keep memory bounded).
- ☐ No code change is required unless the measurement reveals a problem.

---

## R1-07 — Makefile `install` Target Docs Alignment

**Severity:** 🟢 LOW — documentation drift
**Origin:** Phase 0

### Current state

`Makefile` line:

```makefile
install:
	uv sync --directory backend --dev
```

`docs/ENGINEERING.md` §4:

```makefile
install:
	uv sync --directory backend
```

The Makefile uses `--dev` (includes dev dependencies) but the doc doesn't show it. The Makefile is correct (dev deps are needed for lint/typecheck/test).

### Target state

Update ENGINEERING.md §4 to match the Makefile:

```makefile
install:
	uv sync --directory backend --dev
	npm --prefix frontend install
```

### Acceptance criteria

- ☐ ENGINEERING.md §4 `install` target reads `uv sync --directory backend --dev`.
- ☐ No functional change — this is documentation-only.

---

## R1-08 — `package.json` `allowScripts` Documentation

**Severity:** 🟢 LOW — documentation gap
**Origin:** Phase 0

### Current state

`frontend/package.json` contains:

```json
"allowScripts": {
  "esbuild@0.25.12": true,
  "fsevents@2.3.3": true,
  "msw@2.14.6": true
}
```

This is an npm 10+ feature that whitelists which packages' postinstall scripts are allowed to run (a security feature). MSW requires a postinstall script to download its service worker; esbuild and fsevents have native binary install scripts. This configuration is correct but not documented anywhere.

### Target state

Add a brief note in `docs/ENGINEERING.md` §3.1 (under "Runtime & Package Manager") explaining that `allowScripts` is set to whitelist the three packages that need native build/postinstall scripts. This prevents `npm install` from prompting for script approval and documents why these specific packages are trusted.

### Acceptance criteria

- ☐ ENGINEERING.md §3.1 has a sentence or two explaining `allowScripts`.
- ☐ The three whitelisted packages (esbuild, fsevents, msw) are named with their purpose.
- ☐ No functional change.

---

## R1-09 — Dashboard Workout List → Detail Navigation UX

**Severity:** 🟡 MED — UX completeness
**Origin:** Phase 7

### Current state

The workout list renders as a static table. There is no way to navigate from a list row to the detail view.

### Target state

- Each workout row is clickable (cursor pointer + `onClick` handler).
- Clicking a row shows the detail panel for that workout (see R1-01).
- The detail panel includes a "← Back to list" button.
- Navigation is managed via React state: `{ view: 'list' } | { view: 'detail', workoutId: number }`.
- URL does not change (no React Router).

### Acceptance criteria

- ☐ Clicking a workout row in the list transitions to the detail panel for that workout.
- ☐ The detail panel shows the "Back to list" button; clicking it returns to the workout list.
- ☐ Frontend test: simulate click on first row → assert detail component renders with the correct workout ID.
- ☐ Frontend test: simulate back button → assert list is shown again.
- ☐ Keyboard accessibility: rows are focusable and respond to Enter/Space.
- ☐ Typecheck + lint pass.

---

## R1-10 — Per-Module Coverage Enforcement

**Severity:** 🟡 MED — quality gate gap
**Origin:** Phase 0

### Current state

The global coverage gate (`--cov-fail-under=80`) is enforced. Per-module goals (ingest ≥90%, llm ≥70%) are tracked manually per ENGINEERING.md §2.4, but there's no CI enforcement:

> If we later want these enforced, add a CI step after the pytest run that reads the
> existing coverage data, e.g.
> `uv run --directory backend coverage report --include="app/ingest/*" --fail-under=90`

### Target state

Add a CI step (or a Makefile target wired into CI) that enforces per-module coverage:

```makefile
# In Makefile
coverage-modules:
	uv run --directory backend coverage report --include="app/ingest/*" --fail-under=90
	uv run --directory backend coverage report --include="app/llm/*" --fail-under=70
```

Add this as a new CI job in `.github/workflows/ci.yml` that runs *after* `test-backend` (it reads `backend/.coverage` from the test run). Alternatively, fold it into the existing `test-backend` job as additional steps.

If current coverage doesn't meet these thresholds, bring them up to target before enforcing. The agent claims 89.7% overall — verify actual per-module numbers first.

### Acceptance criteria

- ☐ CI job (or step in test-backend) runs `coverage report --include="app/ingest/*" --fail-under=90`.
- ☐ CI job (or step) runs `coverage report --include="app/llm/*" --fail-under=70`.
- ☐ Both pass on the current codebase (or coverage is improved to meet the threshold).
- ☐ ENGINEERING.md §2.4 is updated to say the per-module gates are now CI-enforced.

---

## R1-11 — ChatResponse `data` Typing: `Any` → Discriminated Union

**Severity:** 🟡 MED — type safety
**Origin:** Phase 4

### Current state

`backend/app/models/chat.py`:

```python
class ChatResponse(BaseModel):
    template_id: str
    data: dict[str, Any]    # ← Any loses all type information
    narrative: str
```

The response model uses `dict[str, Any]` for the `data` field, which means neither Pyright nor FastAPI's OpenAPI schema knows the shape of template data. The `data` field should be a discriminated union keyed on `template_id`, but Pydantic v2's discriminated unions require a literal discriminator on a nested field, not the parent. Since `template_id` is a sibling of `data`, a clean discriminated union is awkward in Pydantic v2.

### Target state

**Option A — Validated generic (recommended).** Add a `model_post_init` validator that checks `data` against the corresponding Pydantic template model based on `template_id`. This doesn't change the type annotation but adds runtime validation:

```python
from pydantic import model_validator

class ChatResponse(BaseModel):
    template_id: str
    data: dict[str, Any]
    narrative: str

    @model_validator(mode="after")
    def _validate_data(self) -> "ChatResponse":
        model = _TEMPLATE_MODELS.get(self.template_id)
        if model is not None:
            model.model_validate(self.data)
        return self
```

Where `_TEMPLATE_MODELS` maps `template_id` → Pydantic model class.

**Option B — Union type.** Use `Annotated` + `Union` with Pydantic v2 discriminated unions, though the sibling-field constraint makes this less ergonomic. Only pursue this if Pydantic supports it cleanly.

### Acceptance criteria

- ☐ `ChatResponse` validation rejects a `data` dict that doesn't match the schema for `template_id` (test: send valid `workout_card` data with `template_id: "trend_chart"` → validation error).
- ☐ The orchestrator's `ChatResponse` construction already validates via `model_dump` of the template model, so no production code changes are needed beyond the response model.
- ☐ A new unit test in `tests/unit/test_models.py` asserts the validator catches mismatched data.
- ☐ Pyright + pytest pass.

---

## R1-12 — Frontend Health-Check Before First Chat Request

**Severity:** 🟢 LOW — UX polish
**Origin:** Phase 6

### Current state

SPEC §3 says `GET /health` is "used by the frontend to verify backend connectivity before sending chat requests." The frontend does not currently call `/health`. If the backend is down, the user types a question, waits for a fetch timeout, and sees a generic error.

### Target state

On the `ChatView` mount (or the first render), call `GET /health`. If it fails (non-200, timeout), show a banner: "Cannot connect to the backend. Make sure `make dev` is running on port 8000." If it succeeds, show the normal chat input.

The health check should:
- Fire once on mount.
- Time out after 3 seconds.
- Not block the chat input from being rendered (the user can still try to type, but they'll see the banner).

### Acceptance criteria

- ☐ Frontend test (MSW): Health endpoint returns 200 → no banner shown.
- ☐ Frontend test (MSW): Health endpoint returns 500 → banner shown.
- ☐ Frontend test (MSW): Health endpoint times out → banner shown.
- ☐ The banner does not prevent the user from typing a question (non-blocking).
- ☐ Typecheck + lint pass.

---

## Implementation Ordering

Recommended order (each numbered group can run in parallel):

```
Group A (backend):  R1-01 (workout detail endpoint), R1-11 (ChatResponse typing)
Group B (frontend): R1-01 (detail view), R1-04 (rings gauge), R1-09 (navigation)
Group C (docs):     R1-02 (pyright config), R1-07 (Makefile docs), R1-08 (allowScripts)
Group D (ci):       R1-10 (per-module coverage), R1-06 (peak RSS verification)
Group E (misc):     R1-03 (gps_route hardening), R1-05 (store cleanup), R1-12 (health check)
```

### Dependency graph

```
R1-02 (pyright) ── independent
R1-03 (gps_route) ── independent
R1-04 (rings gauge) ── independent
R1-05 (store cleanup) ── independent
R1-06 (peak RSS) ── independent
R1-07 (Makefile docs) ── independent
R1-08 (allowScripts docs) ── independent
R1-10 (coverage) ── independent (wires into CI after other backend work)
R1-11 (ChatResponse typing) ── independent
R1-12 (health check) ── independent

R1-01 (backend endpoint) ──────────────────┐
R1-09 (navigation) ── depends on R1-01 ────┘
```

---

## Quality Gates (apply to every fix)

Every fix must pass before merge:
- **Backend:** Ruff check + format, Pyright, pytest (all tests), coverage ≥80%.
- **Frontend:** oxlint, Prettier check, `tsc --noEmit`, Vitest (all tests), coverage (80/80/80/70 thresholds).
- **CI:** The branch must be green on all CI jobs.
- **Pre-commit:** `pre-commit run --all-files` passes.
- **No new `type: ignore` without a comment explaining why.**

---

*Created: 2026-06-27. Derived from the full project review. Each R1-XX item traces back to a
specific gap identified in that review. Update statuses inline as work proceeds.*
