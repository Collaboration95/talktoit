// Chart.js chart components — individual exports for type-first gallery
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Tooltip, Legend, Filler, type ChartOptions,
} from 'chart.js'
import { Line, Bar, Doughnut, Scatter } from 'react-chartjs-2'
import data, { PALETTE, TOP_SPORTS } from '../data'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend, Filler)

const tf = { font: { size: 10 } }

const weeklySteps = buildWeeklySteps()
const rings = data.activityRings
const pct = (v: number, g: number) => Math.round((v / g) * 100)

export function ChartJsArea() {
  const opts: ChartOptions<'line'> = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { ticks: { ...tf, maxTicksLimit: 6 } }, y: { ticks: tf } },
  }
  return (
    <Line
      data={{
        labels: data.restingHrDaily.map(d => d.date.slice(5)),
        datasets: [{ data: data.restingHrDaily.map(d => d.value), borderColor: PALETTE[0], backgroundColor: `${PALETTE[0]}26`, fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 }],
      }}
      options={opts}
    />
  )
}

export function ChartJsBar() {
  const opts: ChartOptions<'bar'> = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { x: { ticks: { ...tf, maxTicksLimit: 8 } }, y: { ticks: tf } },
  }
  return (
    <Bar
      data={{
        labels: weeklySteps.map(w => w.week),
        datasets: [{ data: weeklySteps.map(w => w.steps), backgroundColor: PALETTE[0], borderRadius: 4 }],
      }}
      options={opts}
    />
  )
}

export function ChartJsStacked() {
  const opts: ChartOptions<'bar'> = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { font: { size: 9 }, boxWidth: 10, padding: 8 } } },
    scales: { x: { stacked: true, ticks: { ...tf, maxTicksLimit: 8 } }, y: { stacked: true, ticks: tf } },
  }
  return (
    <Bar
      data={{
        labels: data.weeklyVolumeBySport.map(w => w.week.slice(5)),
        datasets: TOP_SPORTS.map((s, i) => ({
          label: s, data: data.weeklyVolumeBySport.map(w => w[s] as number),
          backgroundColor: PALETTE[i % PALETTE.length], borderRadius: 2,
        })),
      }}
      options={opts}
    />
  )
}

export function ChartJsDonut() {
  const opts: ChartOptions<'doughnut'> = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'right', labels: { font: { size: 9 }, boxWidth: 10 } } },
  }
  return (
    <Doughnut
      data={{
        labels: data.sportBreakdown.map(s => s.type),
        datasets: [{ data: data.sportBreakdown.map(s => s.count), backgroundColor: data.sportBreakdown.map((_, i) => PALETTE[i % PALETTE.length]) }],
      }}
      options={opts}
    />
  )
}

export function ChartJsScatter() {
  const opts: ChartOptions<'scatter'> = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { title: { display: true, text: 'min', font: { size: 9 } }, ticks: tf },
      y: { min: 60, max: 180, title: { display: true, text: 'bpm', font: { size: 9 } }, ticks: tf },
    },
  }
  return (
    <Scatter
      data={{ datasets: [{ data: data.workouts.filter(w => w.avgHr).map(w => ({ x: w.durationMin, y: w.avgHr as number })), backgroundColor: `${PALETTE[2]}99` }] }}
      options={opts}
    />
  )
}

export function ChartJsGauge() {
  const opts: ChartOptions<'doughnut'> = {
    responsive: true, maintainAspectRatio: false, cutout: '40%',
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
  }
  return (
    <Doughnut
      data={{
        labels: ['Move', 'Exercise', 'Stand'],
        datasets: [
          { data: [pct(rings.move, rings.moveGoal), 100 - Math.min(100, pct(rings.move, rings.moveGoal))], backgroundColor: [PALETTE[3], '#f1f3f6'], weight: 1 },
          { data: [pct(rings.exercise, rings.exerciseGoal), 100 - Math.min(100, pct(rings.exercise, rings.exerciseGoal))], backgroundColor: [PALETTE[1], '#f1f3f6'], weight: 1 },
          { data: [pct(rings.stand, rings.standGoal), 100 - Math.min(100, pct(rings.stand, rings.standGoal))], backgroundColor: [PALETTE[5], '#f1f3f6'], weight: 1 },
        ],
      }}
      options={opts}
    />
  )
}

function buildWeeklySteps() {
  const m = new Map<string, number>()
  data.stepsDaily.forEach(d => {
    const dt = new Date(d.date)
    const mon = new Date(dt)
    mon.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
    const key = mon.toISOString().slice(5, 10)
    m.set(key, (m.get(key) ?? 0) + d.steps)
  })
  return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([week, steps]) => ({ week, steps }))
}
