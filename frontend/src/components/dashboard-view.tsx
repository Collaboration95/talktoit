import { useEffect, useMemo, useState } from 'react'
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
import { formatDateOnly, formatNumber } from '@/lib/format'

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

function displayActivityType(activityType: string): string {
  return activityType.replace(/^HKWorkoutActivityType/, '').replace(/([a-z])([A-Z])/g, '$1 $2')
}

function formatDate(isoDate: string): string {
  return formatDateOnly(isoDate)
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
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const workoutTypes = useMemo(
    () =>
      [...new Set(workouts.map((workout) => workout.activity_type))].sort((a, b) =>
        displayActivityType(a).localeCompare(displayActivityType(b)),
      ),
    [workouts],
  )
  if (workouts.length === 0) return <NoData />
  const filteredWorkouts = selectedType
    ? workouts.filter((workout) => workout.activity_type === selectedType)
    : workouts

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2" aria-label="Filter workouts by type">
        <button
          type="button"
          aria-pressed={selectedType === null}
          onClick={() => setSelectedType(null)}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            selectedType === null
              ? 'border-blue-600 bg-blue-600 text-white'
              : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-700'
          }`}
        >
          All <span className="opacity-80">{workouts.length}</span>
        </button>
        {workoutTypes.map((type) => {
          const count = workouts.filter((workout) => workout.activity_type === type).length
          const selected = selectedType === type
          return (
            <button
              key={type}
              type="button"
              aria-pressed={selected}
              onClick={() => setSelectedType(selected ? null : type)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                selected
                  ? 'border-blue-600 bg-blue-600 text-white'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-700'
              }`}
            >
              {displayActivityType(type)} <span className="opacity-80">{count}</span>
            </button>
          )
        })}
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full min-w-[680px] text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              <th className="px-3 py-3">Date</th>
              <th className="px-3 py-3">Workout</th>
              <th className="px-3 py-3 text-right">Duration</th>
              <th className="px-3 py-3 text-right">Avg HR</th>
              <th className="px-3 py-3 text-right">Distance</th>
              <th className="px-3 py-3 text-right">Energy</th>
            </tr>
          </thead>
          <tbody>
            {filteredWorkouts.map((w) => (
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
                className="cursor-pointer border-b last:border-0 hover:bg-blue-50/60 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-400"
              >
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{formatDate(w.date)}</td>
                <td className="px-3 py-3 font-medium text-gray-900" title={w.activity_type}>
                  {displayActivityType(w.activity_type)}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
                  {w.duration_minutes !== null ? `${formatNumber(w.duration_minutes, 0)} min` : '—'}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
                  {w.avg_heart_rate !== null ? `${w.avg_heart_rate} bpm` : '—'}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
                  {w.distance_meters !== null
                    ? `${formatNumber(w.distance_meters / 1000, 1)} km`
                    : '—'}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
                  {w.energy_burned_kj !== null ? `${formatNumber(w.energy_burned_kj, 0)} kJ` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
      fetchSummary(),
      fetchWorkouts(),
      fetchTrend('steps', 'day'),
      fetchTrend('heart', 'week'),
      fetchTrend('sleep', 'day'),
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

      <Section title="Activity Rings (Latest available day)">
        <ActivityRingsPanel days={state.summary} />
      </Section>

      <Section title="Recent Workouts (Latest 30 data days)">
        <WorkoutsPanel
          workouts={state.workouts}
          onSelect={(id) => setMode({ view: 'detail', workoutId: id })}
        />
      </Section>

      <Section title="Daily Steps (Latest 30 data days)">
        <TrendPanel trend={state.steps} title="Steps" />
      </Section>

      <Section title="Resting Heart Rate (Latest 90 data days)">
        <TrendPanel trend={state.heart} title="Resting HR" />
      </Section>

      <Section title="Sleep Duration (Latest 30 data days)">
        <TrendPanel trend={state.sleep} title="Sleep" />
      </Section>

      <Section title="Data Sources">
        <CapabilitiesPanel caps={state.capabilities} />
      </Section>
    </div>
  )
}
