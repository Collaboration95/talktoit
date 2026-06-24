import './App.css'
import type { ReactNode } from 'react'

// ── ECharts (area/bar/stacked/donut/calendar) ─────────────────────────────
import { EChartsArea, EChartsBar, EChartsStacked, EChartsDonut, EChartsCalendar } from './charts/echarts'
// ── Victory (bar close-second, stacked close-second) ─────────────────────
import { VictoryBar, VictoryStacked } from './charts/victory'
// ── Chart.js (area close-second, scatter, gauge close-second) ─────────────
import { ChartJsArea, ChartJsScatter, ChartJsGauge } from './charts/chartjs'
// ── Tremor (ranked list, gauge) ───────────────────────────────────────────
import { TremorBarList, TremorRingList } from './charts/tremor'

// ─── types ──────────────────────────────────────────────────────────────────
type LibCell = { lib: string; pkg: string; chart: ReactNode; badge?: string }
type ChartRow = { id: string; title: string; subtitle: string; cells: LibCell[] }

// Badge shorthands
const WIN = '✓ chosen'
const SEC = '≈ close second'

// ─── data ────────────────────────────────────────────────────────────────────
const ROWS: ChartRow[] = [
  {
    id: 'trend', title: 'Trend Line / Area', subtitle: 'Resting heart rate — 6 months',
    cells: [
      { lib: 'ECharts',  pkg: 'echarts-for-react', chart: <EChartsArea />, badge: WIN },
      { lib: 'Chart.js', pkg: 'react-chartjs-2',   chart: <ChartJsArea />, badge: SEC },
    ],
  },
  {
    id: 'bar', title: 'Bar Chart', subtitle: 'Weekly step count',
    cells: [
      { lib: 'ECharts', pkg: 'echarts-for-react', chart: <EChartsBar />,   badge: WIN },
      { lib: 'Victory', pkg: 'victory',            chart: <VictoryBar />,   badge: SEC },
    ],
  },
  {
    id: 'stacked', title: 'Stacked Bar', subtitle: 'Weekly training volume by sport',
    cells: [
      { lib: 'ECharts', pkg: 'echarts-for-react', chart: <EChartsStacked />, badge: WIN },
      { lib: 'Victory', pkg: 'victory',            chart: <VictoryStacked />, badge: SEC },
    ],
  },
  {
    id: 'donut', title: 'Pie / Donut', subtitle: 'Sport breakdown by session count',
    cells: [
      { lib: 'ECharts', pkg: 'echarts-for-react', chart: <EChartsDonut />, badge: WIN },
    ],
  },
  {
    id: 'scatter', title: 'Scatter Plot', subtitle: 'Workouts: duration vs avg heart rate',
    cells: [
      { lib: 'Chart.js', pkg: 'react-chartjs-2', chart: <ChartJsScatter />, badge: WIN },
    ],
  },
  {
    id: 'calendar', title: 'Calendar Heatmap', subtitle: 'Daily steps — drag the range slider to filter intensity',
    cells: [
      { lib: 'ECharts', pkg: 'echarts-for-react', chart: <EChartsCalendar />, badge: '✓ draggable slider' },
    ],
  },
  {
    id: 'ranked', title: 'Ranked List', subtitle: 'Top workouts by average heart rate',
    cells: [
      { lib: 'Tremor', pkg: '@tremor/react', chart: <TremorBarList />, badge: WIN },
    ],
  },
  {
    id: 'gauge', title: 'Activity Rings / Gauge', subtitle: 'Move · Exercise · Stand — % of daily goal',
    cells: [
      { lib: 'Tremor',   pkg: '@tremor/react',   chart: <TremorRingList />, badge: WIN },
      { lib: 'Chart.js', pkg: 'react-chartjs-2', chart: <ChartJsGauge />,   badge: SEC },
    ],
  },
]

// ─── components ──────────────────────────────────────────────────────────────
function LibCard({ lib, pkg, chart, badge }: LibCell) {
  const isWinner = badge === WIN || badge === '✓ draggable slider'
  return (
    <div className={`lib-card${isWinner ? ' lib-card--winner' : ''}`}>
      <div className="lib-card-head">
        <span className="lib-name">{lib}</span>
        <span className="lib-pkg">{pkg}</span>
        {badge && <span className={`lib-badge${isWinner ? ' lib-badge--winner' : ' lib-badge--second'}`}>{badge}</span>}
      </div>
      <div className="chart-canvas">{chart}</div>
    </div>
  )
}

export default function App() {
  const libs = ['ECharts', 'Victory', 'Chart.js', 'Tremor']
  return (
    <div className="layout">
      <nav className="sidenav">
        <h1>tti · charts</h1>
        <p className="sidenav-meta">Final picks · Apple Health data</p>

        <div className="sidenav-section-label">Chart types</div>
        {ROWS.map(r => (
          <a key={r.id} href={`#${r.id}`}>{r.title}</a>
        ))}

        <div className="sidenav-section-label" style={{ marginTop: 20 }}>Selected libs</div>
        {libs.map(l => <span key={l} className="sidenav-lib">{l}</span>)}
      </nav>

      <main className="content">
        <div className="intro">
          <h1>Chart Library Picks</h1>
          <p>Final selections from the comparison. Winner shown first, close second kept for future swap-out. Nivo, shadcn, Recharts and others dropped.</p>
        </div>

        {ROWS.map(row => (
          <section key={row.id} id={row.id} className="type-section">
            <div className="type-head">
              <h2>{row.title}</h2>
              <span className="type-sub">{row.subtitle}</span>
            </div>
            <div className="lib-row">
              {row.cells.map(cell => (
                <LibCard key={cell.lib} {...cell} />
              ))}
            </div>
          </section>
        ))}
      </main>
    </div>
  )
}
