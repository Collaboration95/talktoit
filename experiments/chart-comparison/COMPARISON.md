# Chart Library Comparison — tti

Evaluated against the same 6-month Apple Health dataset (real data, never committed).
All libraries are **free / open-source**, rendered in **light mode**, React + TypeScript + Vite.
Two rounds of review. Final picks recorded below.

---

## Final Picks (Round 2 — 2026-06-24)

| Chart type | Winner | Close second | Reason |
|---|---|---|---|
| Trend Line / Area | **ECharts** | Chart.js | Smoothest rendering, hover tooltip quality |
| Bar | **ECharts** | Victory | Clean defaults, interactive tooltips |
| Stacked Bar | **ECharts** | Victory | ECharts legend + stack is first-class; Victory's stacked bar also looks great |
| Pie / Donut | **ECharts** | — | Outclassed everything else |
| Scatter | **Chart.js** | — | Clear, correct axis labels out of the box |
| Calendar Heatmap | **ECharts** | — | Draggable `calculable` visualMap is unique; Nivo dropped |
| Ranked List | **Tremor** BarList | — | No other library has an equivalent |
| Activity Rings | **Tremor** BarList-style | Chart.js | Tremor's BarList ring summary is clear; Chart.js concentric doughnut works as backup |

**Primary libraries going into tti:**
1. **Apache ECharts** (`echarts-for-react`) — trend, bar, stacked, donut, calendar
2. **Chart.js** (`react-chartjs-2`) — scatter, activity rings backup, area backup
3. **Tremor** (`@tremor/react`) — ranked list, activity rings summary

Victory retained as a close-second source file only (not imported unless ECharts is swapped).

---

## Library Overview

| Library | License | Gzip est. | Verdict |
|---|---|---|---|
| **Apache ECharts** | Apache 2.0 | ~450 kB | ✅ **Primary** — best-looking out of the box, gauge + calendar are first-class |
| **Chart.js** | MIT | ~220 kB | ✅ **Primary** — best scatter; reliable close-second for everything else |
| **Tremor** | Apache 2.0 | ~95 kB | ✅ **Targeted** — BarList + ring summary only; Tailwind-native |
| **Victory** | MIT | ~260 kB | 🔵 Close second — stacked bar looks excellent; on deck if ECharts is swapped |
| **Nivo** | MIT | ~310 kB | ❌ Dropped Round 2 — good aesthetics but not meaningfully better than ECharts |
| **shadcn/ui** | MIT | — | ❌ Dropped Round 2 — recharts underneath; not distinct enough to justify |
| **Recharts** | MIT | ~180 kB | ❌ Dropped Round 1 |
| **visx** | MIT | ~120 kB | ❌ Dropped Round 1 — too low-level for a product |
| **Observable Plot** | ISC | ~175 kB | ❌ Dropped Round 1 — imperative DOM API doesn't fit React |

---

## Gallery

The comparison app is at `experiments/chart-comparison/`. Source files for all libraries
live in `src/charts/` even for dropped libraries (reference + future swap-out).
Only the winning cells are rendered in `src/App.tsx`.

```bash
cd experiments/chart-comparison
npm install
npm run dev       # → http://localhost:5173 (or next free port)
```

`chart_data.json` is gitignored (derived from private health data). Regenerate with:

```bash
python3 extract_data.py   # requires personal-assets/test-data/export_last6mo.xml
```

### ECharts standout: draggable calendar heatmap
`calculable: true` on the `visualMap` component enables a draggable range slider over the
heatmap — lets you isolate high-step vs low-step days interactively. No other library in the
comparison offers this as a first-class primitive.

---

## Round 1 notes (2026-06-23)

Initial gallery had all 8 libraries in a per-library layout. Switched to **type-first columns**
after Round 1: same chart type across all libraries in one scrollable row makes comparison
immediate. Visx, Observable Plot, Recharts cut after Round 1. Nivo, shadcn/ui cut after Round 2.
