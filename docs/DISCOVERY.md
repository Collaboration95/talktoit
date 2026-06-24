# tti (talk-to-it) — Discovery & Decisions Log

> Living record of decisions made during project discovery. Source of truth for the
> formal spec that follows. Last updated: 2026-06-23.

---

## 1. Project Vision

**tti** = **talk-to-it**.

A **self-hostable, MIT-licensed, open-source** web app that lets anyone explore their own
Apple Health export. The intended user flow:

1. Clone the repo, drop in their own Apple Health export, set an LLM API key in env.
2. Run an ingestion command (one-time) to parse the export into a local database.
3. Start the server → opens a localhost webpage.
4. **Dashboard:** a lightweight port of the Apple Fitness app — simple metrics for
   last week / month / year.
5. **Chat area:** ask plain-language questions ("show me my last long run", "highest
   avg-HR gym session last month") and get answers rendered through **pre-made UI
   templates with real values injected** — a workout card, a trend chart, a ranked
   list — not just prose.

**Philosophy:** the dashboard is the "solved" part (port of a known app). The
conversational layer is the interesting/harder part — start with a few simple,
known queries; expand the toolset later. The *architecture* stays fixed; the set of
tools and templates grows.

---

## 2. Confirmed Decisions

### Stack
- **Backend:** Python. (No Go/Rust — keep it simple.)
- **Frontend:** React + **TypeScript** + Vite. (Not Svelte — no user experience with it. TS over JS.)
- **Backend web framework:** FastAPI (default — to confirm, but consistent with Python + serving a built frontend).
- **Styling:** **Tailwind CSS v3.** Not an independent preference so much as a *consequence*:
  `@tremor/react` (chosen for Ranked List + Activity Rings, §6) is built on Tailwind and only
  supports Tailwind **v3** (not the v4 CSS-first rewrite). So Tailwind is load-bearing and
  pinned to `^3` for as long as Tremor v3 is in the stack. Revisit if/when we adopt a
  Tailwind-v4-compatible Tremor or drop Tremor. (See ENGINEERING §3.5.)
- **One `run` command** should boot the server and serve the built frontend so
  `clone → run` stays simple, even though it's two languages.

### Data & ingestion
- Ingestion is a **separate explicit command** (e.g. a `make ingest` target). Not auto on boot.
- Parsed DB is **DuckDB**, stored as a file **local/relative to the project**.
- The **raw Apple Health export can live anywhere**; its path is configured (env/config).
- Ingestion of the full 2.1 GB / ~4.97M-record export takes ~5–15 min (acceptable as a one-time step).

### LLM provider
- Target **OpenAI-compatible API** (works with **Groq's** OpenAI-compatible endpoint,
  OpenAI itself, local servers, etc.). Provider/base-URL/model configured via env.
- This is an **OpenAI-compatible integration**, not Anthropic-specific.

### Privacy (core principle)
- **Raw data is never sent to the LLM.** The LLM operates entirely through tools.
- Tools run queries and return **structured data**; only a **small slice** of that data
  reaches the LLM — just enough to compose the final natural-language framing and to
  pick which template + values to render.
- The LLM doesn't need to see every datapoint to know how to display it. The bulk of
  the data flows tool → frontend template, bypassing the model.
- This privacy stance is documented in the README.

### Chat → template architecture (the core)
- The LLM is given a **catalog of templates** + a **set of trusted query tools**.
- For a question, the LLM calls tools, then returns a **structured payload that
  designates a template ID + the values to inject**.
- The LLM **never hand-writes SQL that the user sees**; all data access is via the
  defined tools/methods.
- Toolset and template catalog **expand over time**; the architecture does not change.
- **v1 is one-shot** (no multi-turn / follow-up context). Multi-turn comes later.
- Unmatched/open-ended questions → **generic fallback template** (table + short text). *(default, to reconfirm)*

### v1 Template catalog (all approved)
1. **Single workout card** — one session: type, date, duration, avg/max HR, distance, map if GPS.
2. **Ranked list** — e.g. "top 5 gym sessions by avg HR".
3. **Metric trend chart** — a metric over week/month/year.
4. **Period summary** — totals for last week/month: workouts, distance, active energy.
5. **Comparison** — this period vs last.

### v1 Dashboard (non-chat) scope (approved)
- Activity rings / energy
- Workout list + per-workout detail
- Steps / distance
- Resting HR & HRV trend
- Sleep duration
- **Graceful degradation:** other people's exports won't have AutoSleep/Bevel/Runna —
  v1 shows only the panels for which data is present. *(assumed yes — reconfirm)*

### Non-goals for v1
- No multi-user accounts.
- No cloud hosting (localhost only).
- No writing data back to Apple Health.
- No deep multi-year statistical analysis.
- No multi-turn chat (deferred).

### Testing
- Create a **reduced test export** (≈ last 6 months of data) from the full export so
  tests don't run against the 2 GB DB. Exact method TBD; can stream-filter `export.xml`
  by `startDate`.

---

## 3. Round 2 Decisions

- **Charts library:** NOT yet chosen — must be **free/open-source** (no paid chart
  vendors) AND **best-looking available**, because charts are front-and-center and a
  shitty chart undermines the product. Action item: research top free React chart
  libs and pick on looks + license. (Recharts is the baseline candidate, not the
  decision.)
- **UI elsewhere:** **barebones is fine for now.** Only charts/visualizations get
  polish in this phase. Proper UI comes later (designed in Figma) once core
  functionality works.
- **Python tooling:** `uv` + Python 3.12 + a `Makefile` (`make ingest`, `make dev`, …). ✅
- **Repo layout:** monorepo — `backend/`, `frontend/`, `docs/`, MIT `LICENSE` at root. ✅
- **Default model:** Groq-hosted **`llama-3.3-70b-versatile`** (tool-calling capable),
  all overridable via env (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Future
  aspiration: locally-hosted small model (e.g. Gemma) as an improvement, not v1. ✅
- **Initial question set:** all 6 seed questions approved as the v1 launch set:
  1. "Show me my last long run" → single workout card
  2. "My highest average-HR gym session last month" → workout card / ranked-list-of-1
  3. "Top 5 longest runs this year" → ranked list
  4. "How has my resting heart rate trended this year?" → trend chart
  5. "How much did I train last week?" → period summary
  6. "Compare my running this month vs last month" → comparison

### Still open (later)
- Final chart library pick (pending research).
- Backend ↔ frontend `{template_id, data}` payload contract details.
- Fallback-template + graceful-degradation behavior (reconfirm at spec time).

## 3b. Test data subset — DONE
- File: `personal-assets/test-data/export_last6mo.xml` (never committed).
- Built by stream-filtering the original **read-only** (original never modified).
- Cutoff `2025-12-17` (inclusive) → range `2025-12-17 … 2026-06-17`.
- 597 MB (vs 2.1 GB). Kept: 1,352,487 Record · 342 Workout · 183 ActivitySummary · ExportDate · Me.
- Validated well-formed. Filter script: scratchpad `make_subset.py` (fold into the
  repo's tooling later, e.g. `make test-fixture`).
- Note: 6 months is still 597 MB (dominated by high-frequency HR records). If unit
  tests need something tiny, a 1-month or single-day fixture can be cut the same way.

---

## 5. Chart Library Selection — Round 1 Gallery Review (2026-06-23)

Live gallery built at `experiments/chart-comparison/` using real Apple Health data.
All libraries rendered side-by-side in a type-first column layout.

### Removed from contention after Round 1
- **Recharts** — dropped
- **visx** — dropped (too low-level / verbose for a product)
- **Observable Plot** — dropped (imperative DOM append doesn't fit React component trees)

### Surviving after Round 1
| Library | Standout |
|---|---|
| **Apache ECharts** | Draggable calendar heatmap (`calculable: true` visualMap) is the headline feature |
| **Victory** | Stacked-bar (weekly volume by sport) looked best with proper `VictoryStack` + `VictoryLegend` |
| **Tremor** | BarList ranked chart is uniquely useful — keep it |
| **Chart.js** | Solid labels/legends, good scatter and gauge |
| **Nivo** | Kept for a second look |
| **shadcn/ui** | Added to gallery (recharts-based with CSS-variable theming) |

### Layout decision
Type-first columns: each row = one chart type, all libraries side-by-side. Interactive > static.

---

## 6. Chart Library Selection — Round 2 Final Picks (2026-06-24)

Second pass after seeing all libraries rendered together.

### Dropped entirely
- **Nivo** — out completely
- **shadcn/ui** — out (recharts under the hood; not distinct enough)
- **Tremor** — out *except* for Activity Rings (Tremor BarList kept)

### Final selection by chart type

| Chart type | Winner | Close second (kept for future swap) |
|---|---|---|
| Trend Line / Area | **ECharts** | Chart.js |
| Bar Chart | **ECharts** | Victory |
| Stacked Bar | **ECharts** | Victory |
| Pie / Donut | **ECharts** | — |
| Scatter Plot | **Chart.js** | — |
| Calendar Heatmap | **ECharts** | — (Nivo dropped; no real competitor) |
| Ranked List | **Tremor** BarList | — |
| Activity Rings / Gauge | **Tremor** BarList-style | Chart.js concentric doughnut |

### Bottom line: two primary libraries
- **Apache ECharts** — primary chart library for almost everything (trend, bar, stacked, donut, calendar)
- **Chart.js** — scatter, activity rings close-second, area close-second
- **Tremor** — retained only for Ranked List and Activity Rings gauge
- **Victory** — retained only as bar/stacked-bar close-second

### Implementation note
`experiments/chart-comparison/src/charts/` retains source files for all libraries.
Only the selected cells appear in App.tsx; close-second files stay on disk for future reference.
Bundle shrank from ~3.3 MB → ~2.6 MB after removing Nivo and shadcn from the rendered gallery.

---

## 4. Data Reference (from earlier analysis)

- Source export: `personal-assets/june18/export.xml` (2.1 GB, ~4.97M records, 3,026 workouts,
  1,450 ring-days; Oct 2017 – Jun 2026; SGT +0800). Schema fully documented in
  `personal-assets/STRUCTURE.md`. Ingestion plan in `personal-assets/INGESTION-NOTES.md`.
- `personal-assets/` is **never committed** (contains personal data).
