import { useEffect, useState } from 'react'
import { TrendLine } from '@/charts/trend-line'
import type {
  ActivityRingDay,
  CapabilityFlag,
  TrendResponse,
  WorkoutSummary,
} from '@/api/dashboard'
import { fetchCapabilities, fetchSummary, fetchTrend, fetchWorkouts } from '@/api/dashboard'

interface DashboardState {
  summary: ActivityRingDay[]
  workouts: WorkoutSummary[]
  steps: TrendResponse | null
  heart: TrendResponse | null
  sleep: TrendResponse | null
  capabilities: CapabilityFlag[]
  loading: boolean
  error: string | null
}

function fmt(val: number | null, unit = ''): string {
  if (val === null || val === undefined) return '—'
  return `${Math.round(val * 10) / 10}${unit ? ' ' + unit : ''}`
}

function NoData() {
  return <p className="text-sm text-gray-400 py-4">No data</p>
}

function ActivityRingsPanel({ days }: { days: ActivityRingDay[] }) {
  if (days.length === 0) return <NoData />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            <th className="pb-2 pr-4">Date</th>
            <th className="pb-2 pr-4">Energy (kJ)</th>
            <th className="pb-2 pr-4">Exercise (min)</th>
            <th className="pb-2">Stand (hrs)</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.date} className="border-b last:border-0">
              <td className="py-1 pr-4 font-medium">{d.date}</td>
              <td className="py-1 pr-4">
                {fmt(d.energy_kj)}
                {d.energy_goal_kj !== null && (
                  <span className="text-gray-400"> / {fmt(d.energy_goal_kj)}</span>
                )}
              </td>
              <td className="py-1 pr-4">
                {fmt(d.exercise_min)}
                {d.exercise_goal_min !== null && (
                  <span className="text-gray-400"> / {fmt(d.exercise_goal_min)}</span>
                )}
              </td>
              <td className="py-1">
                {fmt(d.stand_hours)}
                {d.stand_goal_hours !== null && (
                  <span className="text-gray-400"> / {d.stand_goal_hours}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function WorkoutsPanel({ workouts }: { workouts: WorkoutSummary[] }) {
  if (workouts.length === 0) return <NoData />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b">
            <th className="pb-2 pr-4">Date</th>
            <th className="pb-2 pr-4">Type</th>
            <th className="pb-2 pr-4">Duration</th>
            <th className="pb-2 pr-4">Avg HR</th>
            <th className="pb-2 pr-4">Distance</th>
            <th className="pb-2">Energy</th>
          </tr>
        </thead>
        <tbody>
          {workouts.map((w) => (
            <tr key={w.id} className="border-b last:border-0">
              <td className="py-1 pr-4 text-gray-500">{w.date.slice(0, 10)}</td>
              <td className="py-1 pr-4 font-medium">{w.activity_type}</td>
              <td className="py-1 pr-4">{fmt(w.duration_minutes, 'min')}</td>
              <td className="py-1 pr-4">
                {w.avg_heart_rate !== null ? `${w.avg_heart_rate} bpm` : '—'}
              </td>
              <td className="py-1 pr-4">
                {w.distance_meters !== null ? fmt(w.distance_meters / 1000, 'km') : '—'}
              </td>
              <td className="py-1">{fmt(w.energy_burned_kj, 'kJ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TrendPanel({ trend, title }: { trend: TrendResponse | null; title: string }) {
  if (!trend || trend.series.length === 0) return <NoData />
  const hasData = trend.series.some((p) => p.value !== null)
  if (!hasData) return <NoData />
  return (
    <TrendLine
      series={trend.series}
      metricLabel={trend.metric_label}
      metricUnit={trend.metric_unit}
      title={title}
    />
  )
}

function CapabilitiesPanel({ caps }: { caps: CapabilityFlag[] }) {
  if (caps.length === 0) return <NoData />
  return (
    <div className="flex flex-wrap gap-2">
      {caps.map((c) => (
        <span
          key={c.name}
          className={`px-2 py-1 rounded text-xs font-medium ${
            c.present ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'
          }`}
        >
          {c.name.replace('_', ' ')} {c.present ? '✓' : '✗'}
        </span>
      ))}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h2 className="text-base font-semibold text-gray-800 mb-3">{title}</h2>
      {children}
    </section>
  )
}

export function DashboardView() {
  const [state, setState] = useState<DashboardState>({
    summary: [],
    workouts: [],
    steps: null,
    heart: null,
    sleep: null,
    capabilities: [],
    loading: true,
    error: null,
  })

  useEffect(() => {
    Promise.all([
      fetchSummary(7),
      fetchWorkouts(30),
      fetchTrend('steps', 30, 'day'),
      fetchTrend('heart', 90, 'week'),
      fetchTrend('sleep', 30, 'day'),
      fetchCapabilities(),
    ])
      .then(([summary, workouts, steps, heart, sleep, caps]) => {
        setState({
          summary,
          workouts,
          steps,
          heart,
          sleep,
          capabilities: caps,
          loading: false,
          error: null,
        })
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load dashboard'
        setState((prev) => ({ ...prev, loading: false, error: msg }))
      })
  }, [])

  if (state.loading) {
    return (
      <div
        className="flex items-center justify-center min-h-64 text-gray-500"
        data-testid="loading"
      >
        Loading dashboard…
      </div>
    )
  }

  if (state.error) {
    return (
      <div className="flex items-center justify-center min-h-64 text-red-500">
        Error: {state.error}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-4">
      <Section title="Activity Rings (Last 7 Days)">
        <ActivityRingsPanel days={state.summary} />
      </Section>

      <Section title="Recent Workouts (Last 30 Days)">
        <WorkoutsPanel workouts={state.workouts} />
      </Section>

      <Section title="Daily Steps (Last 30 Days)">
        <TrendPanel trend={state.steps} title="Steps" />
      </Section>

      <Section title="Resting Heart Rate (Last 90 Days)">
        <TrendPanel trend={state.heart} title="Resting HR" />
      </Section>

      <Section title="Sleep Duration (Last 30 Days)">
        <TrendPanel trend={state.sleep} title="Sleep" />
      </Section>

      <Section title="Data Sources">
        <CapabilitiesPanel caps={state.capabilities} />
      </Section>
    </div>
  )
}
