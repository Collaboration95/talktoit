import { useEffect, useMemo, useState } from 'react'
import { TrendLine } from '@/charts/trend-line'
import { GaugeRings } from '@/charts/gauge-rings'
import { WorkoutDetail } from '@/components/workout-detail'
import type {
  ActivityRingDay,
  CapabilityFlag,
  DatasetStatus,
  SleepStagesResponse,
  TrendResponse,
  WorkoutSummary,
} from '@/api/dashboard'
import {
  fetchCapabilities,
  fetchDatasetStatus,
  fetchSleepStages,
  fetchSummary,
  fetchTrend,
  fetchWorkouts,
} from '@/api/dashboard'
import type { DashboardScope } from '@/api/dashboard'
import { decodeDashboardQuery, encodeDashboardQuery } from '@/lib/dashboard-query'
import type { DashboardQuery } from '@/lib/dashboard-query'
import { createSavedView, listSavedViews } from '@/api/saved-views'
import type { SavedView } from '@/api/saved-views'
import { formatDateOnly, formatNumber } from '@/lib/format'

type DashboardViewMode = { view: 'list' } | { view: 'detail'; workoutId: number }

interface DashboardState {
  summary: ActivityRingDay[]
  workouts: WorkoutSummary[]
  steps: TrendResponse | null
  heart: TrendResponse | null
  sleep: TrendResponse | null
  sleepStages: SleepStagesResponse | null
  capabilities: CapabilityFlag[]
  datasetStatus: DatasetStatus | null
  nextWorkoutCursor: string | null
  loading: boolean
  error: string | null
  failedPanels: string[]
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

function requestSignal(controller: AbortController): AbortSignal | undefined {
  // jsdom supplies an AbortSignal that Node's fetch implementation cannot
  // consume. Browsers use a compatible implementation and receive cancellation.
  return typeof navigator !== 'undefined' && navigator.userAgent.includes('jsdom')
    ? undefined
    : controller.signal
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

function SleepStagesPanel({ stages }: { stages: SleepStagesResponse | null }) {
  if (!stages) return <NoData />
  if (!stages.stage_data_available) return <p className="text-sm text-gray-500">{stages.message}</p>
  return (
    <div className="space-y-2 text-sm">
      <p className="text-gray-600">
        Measured asleep time: {formatNumber(stages.total_asleep_hours, 1)} h
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1" aria-label="Measured sleep stage durations">
        {Object.entries(stages.stages_hours)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([stage, hours]) => (
            <div key={stage} className="flex justify-between gap-3">
              <dt className="text-gray-500">{stage}</dt>
              <dd className="tabular-nums text-gray-800">{formatNumber(hours, 1)} h</dd>
            </div>
          ))}
      </dl>
      <p className="text-xs text-gray-500">{stages.message}</p>
    </div>
  )
}

function SavedViewsPanel({
  views,
  onApply,
}: {
  views: SavedView[]
  onApply: (query: DashboardQuery) => void
}) {
  if (!views.length) return null
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Saved dashboard views">
      <span className="text-sm text-gray-500">Saved views:</span>
      {views.map((view) => (
        <button
          key={view.id}
          type="button"
          className="rounded border border-gray-300 px-2 py-1 text-sm text-blue-700"
          onClick={() => onApply(view.query)}
        >
          {view.title}
        </button>
      ))}
    </div>
  )
}

function WorkoutsPanel({
  workouts,
  nextWorkoutCursor,
  scope,
  onScopeChange,
  onLoadMore,
  onSelect,
}: {
  workouts: WorkoutSummary[]
  nextWorkoutCursor: string | null
  scope: DashboardScope
  onScopeChange: (scope: DashboardScope) => void
  onSelect: (id: number) => void
  onLoadMore: () => void
}) {
  const workoutTypes = useMemo(
    () =>
      [...new Set(workouts.map((workout) => workout.activity_type))].sort((a, b) =>
        displayActivityType(a).localeCompare(displayActivityType(b)),
      ),
    [workouts],
  )
  const sources = useMemo(
    () => [...new Set(workouts.map((workout) => workout.source_name))].sort(),
    [workouts],
  )
  if (workouts.length === 0) return <NoData />

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2" aria-label="Filter workouts by type">
        <button
          type="button"
          aria-pressed={!scope.activityType}
          onClick={() => {
            const { activityType: _activityType, ...withoutType } = scope
            onScopeChange(withoutType)
          }}
          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
            !scope.activityType
              ? 'border-blue-600 bg-blue-600 text-white'
              : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300 hover:text-blue-700'
          }`}
        >
          All <span className="opacity-80">{workouts.length}</span>
        </button>
        {workoutTypes.map((type) => {
          const count = workouts.filter((workout) => workout.activity_type === type).length
          const selected = scope.activityType === type
          return (
            <button
              key={type}
              type="button"
              aria-pressed={selected}
              onClick={() => {
                if (selected) {
                  const { activityType: _activityType, ...withoutType } = scope
                  onScopeChange(withoutType)
                  return
                }
                onScopeChange({ ...scope, activityType: type })
              }}
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
        <label className="ml-auto flex items-center gap-2 text-xs text-gray-600">
          Source
          <select
            value={scope.source ?? ''}
            aria-label="Filter workouts by source"
            onChange={(event) => {
              if (!event.target.value) {
                const { source: _source, ...withoutSource } = scope
                onScopeChange(withoutSource)
                return
              }
              onScopeChange({ ...scope, source: event.target.value })
            }}
            className="rounded border border-gray-300 bg-white px-2 py-1 text-xs"
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-100">
        <table className="w-full min-w-[680px] text-sm">
          <thead>
            <tr className="border-b bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              <th className="px-3 py-3">Date</th>
              <th className="px-3 py-3">Workout</th>
              <th className="px-3 py-3">Source</th>
              <th className="px-3 py-3 text-right">Duration</th>
              <th className="px-3 py-3 text-right">Avg HR</th>
              <th className="px-3 py-3 text-right">Distance</th>
              <th className="px-3 py-3 text-right">Energy</th>
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
                className="cursor-pointer border-b last:border-0 hover:bg-blue-50/60 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-400"
              >
                <td className="whitespace-nowrap px-3 py-3 text-gray-500">{formatDate(w.date)}</td>
                <td className="px-3 py-3 font-medium text-gray-900" title={w.activity_type}>
                  {displayActivityType(w.activity_type)}
                </td>
                <td className="px-3 py-3 text-gray-500">{w.source_name}</td>
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
      {nextWorkoutCursor ? (
        <button
          type="button"
          className="mt-3 rounded border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700"
          onClick={onLoadMore}
        >
          Load more workouts
        </button>
      ) : null}
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
  const initialQuery = decodeDashboardQuery(window.location.search)
  const [state, setState] = useState<DashboardState>({
    summary: [],
    workouts: [],
    steps: null,
    heart: null,
    sleep: null,
    sleepStages: null,
    capabilities: [],
    datasetStatus: null,
    nextWorkoutCursor: null,
    loading: true,
    error: null,
    failedPanels: [],
  })
  const [mode, setMode] = useState<DashboardViewMode>(() =>
    initialQuery.selectedWorkout
      ? { view: 'detail', workoutId: initialQuery.selectedWorkout }
      : { view: 'list' },
  )
  const [scope, setScope] = useState<DashboardScope>(() => {
    return {
      ...(initialQuery.start && initialQuery.end
        ? { start: initialQuery.start, end: initialQuery.end }
        : {}),
      ...(initialQuery.activityType ? { activityType: initialQuery.activityType } : {}),
      ...(initialQuery.source ? { source: initialQuery.source } : {}),
    }
  })
  const [backendDown, setBackendDown] = useState(false)
  const [savedViews, setSavedViews] = useState<SavedView[]>([])
  const [savedViewTitle, setSavedViewTitle] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  const reloadSavedViews = () => {
    listSavedViews()
      .then(setSavedViews)
      .catch(() => setSavedViews([]))
  }

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
    reloadSavedViews()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const signal = requestSignal(controller)
    let active = true
    Promise.allSettled([
      fetchSummary(scope, signal),
      fetchWorkouts(scope, undefined, signal),
      fetchTrend('steps', 'day', scope, signal),
      fetchTrend('heart', 'week', scope, signal),
      fetchTrend('sleep', 'day', scope, signal),
      fetchSleepStages(scope, signal),
      fetchCapabilities(signal),
      fetchDatasetStatus(signal),
    ]).then((results) => {
      const [
        summaryResult,
        workoutsResult,
        stepsResult,
        heartResult,
        sleepResult,
        stagesResult,
        capsResult,
        statusResult,
      ] = results
      if (
        !active ||
        !summaryResult ||
        !workoutsResult ||
        !stepsResult ||
        !heartResult ||
        !sleepResult ||
        !stagesResult ||
        !capsResult ||
        !statusResult
      ) {
        return
      }
      setState({
        summary: summaryResult.status === 'fulfilled' ? summaryResult.value : [],
        workouts: workoutsResult.status === 'fulfilled' ? workoutsResult.value.workouts : [],
        nextWorkoutCursor:
          workoutsResult.status === 'fulfilled' ? workoutsResult.value.next_cursor : null,
        steps: stepsResult.status === 'fulfilled' ? stepsResult.value : null,
        heart: heartResult.status === 'fulfilled' ? heartResult.value : null,
        sleep: sleepResult.status === 'fulfilled' ? sleepResult.value : null,
        sleepStages: stagesResult.status === 'fulfilled' ? stagesResult.value : null,
        capabilities: capsResult.status === 'fulfilled' ? capsResult.value : [],
        datasetStatus: statusResult.status === 'fulfilled' ? statusResult.value : null,
        loading: false,
        error: null,
        failedPanels: [
          ...(summaryResult.status === 'rejected' ? ['activity rings'] : []),
          ...(workoutsResult.status === 'rejected' ? ['workouts'] : []),
          ...(stepsResult.status === 'rejected' ? ['steps'] : []),
          ...(heartResult.status === 'rejected' ? ['heart rate'] : []),
          ...(sleepResult.status === 'rejected' ? ['sleep'] : []),
          ...(stagesResult.status === 'rejected' ? ['sleep stages'] : []),
          ...(capsResult.status === 'rejected' ? ['data sources'] : []),
          ...(statusResult.status === 'rejected' ? ['import status'] : []),
        ],
      })
    })
    return () => {
      active = false
      controller.abort()
    }
  }, [scope, reloadToken])

  const loadMoreWorkouts = () => {
    if (!state.nextWorkoutCursor) return
    fetchWorkouts(scope, state.nextWorkoutCursor)
      .then((page) => {
        setState((current) => ({
          ...current,
          workouts: [...current.workouts, ...page.workouts],
          nextWorkoutCursor: page.next_cursor,
        }))
      })
      .catch(() => {
        // The currently loaded page remains usable when an additional page fails.
      })
  }

  const updateWorkoutScope = (nextScope: DashboardScope) => {
    const normalized: DashboardScope = {
      ...(nextScope.start ? { start: nextScope.start } : {}),
      ...(nextScope.end ? { end: nextScope.end } : {}),
      ...(nextScope.activityType ? { activityType: nextScope.activityType } : {}),
      ...(nextScope.source ? { source: nextScope.source } : {}),
    }
    const query = decodeDashboardQuery(window.location.search)
    window.history.pushState(
      {},
      '',
      `?${encodeDashboardQuery({ ...query, tab: 'workouts', ...normalized })}`,
    )
    setScope(normalized)
  }

  const selectWorkout = (workoutId: number) => {
    const query = decodeDashboardQuery(window.location.search)
    window.history.pushState(
      {},
      '',
      `?${encodeDashboardQuery({ ...query, tab: 'workouts', selectedWorkout: workoutId })}`,
    )
    setMode({ view: 'detail', workoutId })
  }

  const returnToWorkoutList = () => {
    const { selectedWorkout: _selectedWorkout, ...query } = decodeDashboardQuery(
      window.location.search,
    )
    window.history.pushState({}, '', `?${encodeDashboardQuery(query)}`)
    setMode({ view: 'list' })
  }

  const applySavedView = (query: DashboardQuery) => {
    const nextScope: DashboardScope = {
      ...(query.start && query.end ? { start: query.start, end: query.end } : {}),
      ...(query.activityType ? { activityType: query.activityType } : {}),
      ...(query.source ? { source: query.source } : {}),
    }
    window.history.pushState({}, '', `?${encodeDashboardQuery({ ...query, tab: 'overview' })}`)
    setMode({ view: 'list' })
    setScope(nextScope)
  }

  const saveCurrentView = () => {
    if (!scope.start || !scope.end) return
    createSavedView(savedViewTitle, { tab: 'overview', ...scope })
      .then(() => {
        setSavedViewTitle('')
        reloadSavedViews()
      })
      .catch(() => undefined)
  }

  if (state.loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-6 space-y-4">
        <div
          className="flex items-center justify-center min-h-64 text-gray-500"
          data-testid="loading"
        >
          Loading dashboard…
        </div>
        <SavedViewsPanel views={savedViews} onApply={applySavedView} />
      </div>
    )
  }

  // Workout detail view (R1-09)
  if (mode.view === 'detail') {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <WorkoutDetail workoutId={mode.workoutId} onBack={returnToWorkoutList} />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 space-y-4">
      {backendDown ? <BackendDownBanner /> : null}
      {scope.start && scope.end ? (
        <p className="text-sm text-gray-500" aria-label="Active dashboard scope">
          Showing {scope.start} to {scope.end}
        </p>
      ) : null}
      {state.datasetStatus?.dataset ? (
        <p className="text-xs text-gray-500" aria-label="Imported data coverage">
          Imported coverage: {state.datasetStatus.dataset.coverage_start ?? 'unknown'} to{' '}
          {state.datasetStatus.dataset.coverage_end ?? 'unknown'}
        </p>
      ) : null}
      {state.failedPanels.length > 0 ? (
        <div className="flex items-center gap-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <span>Could not load: {state.failedPanels.join(', ')}.</span>
          <button
            type="button"
            className="font-medium text-blue-700 underline"
            onClick={() => setReloadToken((value) => value + 1)}
          >
            Retry unavailable panels
          </button>
        </div>
      ) : null}
      <SavedViewsPanel views={savedViews} onApply={applySavedView} />
      {scope.start && scope.end ? (
        <div className="flex gap-2" aria-label="Save current dashboard view">
          <input
            value={savedViewTitle}
            onChange={(event) => setSavedViewTitle(event.target.value)}
            placeholder="View name"
            aria-label="Saved view name"
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            className="rounded border px-2 py-1 text-sm"
            onClick={saveCurrentView}
          >
            Save view
          </button>
        </div>
      ) : null}

      <Section title="Activity Rings (Latest available day)">
        <ActivityRingsPanel days={state.summary} />
      </Section>

      <Section title="Recent Workouts (Latest 30 data days)">
        <WorkoutsPanel
          workouts={state.workouts}
          nextWorkoutCursor={state.nextWorkoutCursor}
          scope={scope}
          onScopeChange={updateWorkoutScope}
          onSelect={selectWorkout}
          onLoadMore={loadMoreWorkouts}
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

      <Section title="Measured Sleep Stages">
        <SleepStagesPanel stages={state.sleepStages} />
      </Section>

      <Section title="Data Sources">
        <CapabilitiesPanel caps={state.capabilities} />
      </Section>
    </div>
  )
}
