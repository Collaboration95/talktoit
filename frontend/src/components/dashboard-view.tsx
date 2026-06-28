import { useEffect, useState } from 'react'
import { TrendLine } from '@/charts/trend-line'
import { GaugeRings } from '@/charts/gauge-rings'
import { WorkoutDetail } from '@/components/workout-detail'
import type {
  ActivityRingDay,
  CapabilityFlag,
  TrendResponse,
  WorkoutSummary,
} from '@/api/dashboard'
import { fetchCapabilities, fetchSummary, fetchTrend, fetchWorkouts } from '@/api/dashboard'

type DashboardViewMode = { view: 'list' } | { view: 'detail'; workoutId: number }

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

function NoData() {
  return <p className="text-sm text-gray-400 py-4">No data</p>
}

function ActivityRingsPanel({ days }: { days: ActivityRingDay[] }) {
  if (days.length === 0) return <NoData />
  const latest = days[0]!
  return (
    <GaugeRings
      energy={{ current: latest.energy_kj, goal: latest.energy_goal_kj }}
      exercise={{ current: latest.exercise_min, goal: latest.exercise_goal_min }}
      stand={{ current: latest.stand_hours, goal: latest.stand_goal_hours }}
    />
  )
}

function WorkoutsPanel({
  workouts,
  onSelect,
}: {
  workouts: WorkoutSummary[]
  onSelect: (id: number) => void
}) {
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
            <tr
              key={w.id}
              onClick={() => onSelect(w.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(w.id)
                }
              }}
              tabIndex={0}
              role="button"
              className="border-b last:border-0 cursor-pointer hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:ring-inset"
            >
              <td className="py-1 pr-4 text-gray-500">{w.date.slice(0, 10)}</td>
              <td className="py-1 pr-4 font-medium">{w.activity_type}</td>
              <td className="py-1 pr-4">
                {w.duration_minutes !== null ? `${w.duration_minutes} min` : '—'}
              </td>
              <td className="py-1 pr-4">
                {w.avg_heart_rate !== null ? `${w.avg_heart_rate} bpm` : '—'}
              </td>
              <td className="py-1 pr-4">
                {w.distance_meters !== null
                  ? `${Math.round((w.distance_meters / 1000) * 10) / 10} km`
                  : '—'}
              </td>
              <td className="py-1">
                {w.energy_burned_kj !== null ? `${w.energy_burned_kj} kJ` : '—'}
              </td>
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

/** Banner shown when the backend health check fails (R1-12). */
function BackendDownBanner() {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
      Cannot connect to the backend. Make sure <code className="font-mono">make dev</code> is
      running on port 8000.
    </div>
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
  const [mode, setMode] = useState<DashboardViewMode>({ view: 'list' })
  const [backendDown, setBackendDown] = useState(false)

  // Health check on mount (R1-12)
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 3000)
    fetch('/health', { signal: controller.signal })
      .then((r) => {
        if (!r.ok) setBackendDown(true)
      })
      .catch(() => setBackendDown(true))
      .finally(() => clearTimeout(timer))
  }, [])

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

  // Workout detail view (R1-09)
  if (mode.view === 'detail') {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <WorkoutDetail workoutId={mode.workoutId} onBack={() => setMode({ view: 'list' })} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-4">
      {backendDown ? <BackendDownBanner /> : null}

      <Section title="Activity Rings (Today)">
        <ActivityRingsPanel days={state.summary} />
      </Section>

      <Section title="Recent Workouts (Last 30 Days)">
        <WorkoutsPanel
          workouts={state.workouts}
          onSelect={(id) => setMode({ view: 'detail', workoutId: id })}
        />
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
