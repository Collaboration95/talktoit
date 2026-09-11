import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { TrendLine } from '@/charts/trend-line'
import { GaugeRings } from '@/charts/gauge-rings'
import { WorkoutDetail } from '@/components/workout-detail'
import type {
  ActivityRingDay,
  CapabilityFlag,
  DatasetStatus,
  SleepStagesResponse,
  TrainingVolumeResponse,
  TrendResponse,
  WorkoutSummary,
} from '@/api/dashboard'
import {
  fetchCapabilities,
  fetchDatasetStatus,
  fetchSleepStages,
  fetchSummary,
  fetchTrainingVolume,
  fetchTrend,
  fetchWorkouts,
} from '@/api/dashboard'
import type { DashboardScope } from '@/api/dashboard'
import { decodeDashboardQuery, encodeDashboardQuery } from '@/lib/dashboard-query'
import type { DashboardQuery } from '@/lib/dashboard-query'
import { createSavedView, listSavedViews } from '@/api/saved-views'
import type { SavedView } from '@/api/saved-views'
import { formatDateOnly, formatNumber } from '@/lib/format'
import { useBackendHealth } from '@/lib/use-backend-health'
import { BackendDownBanner } from '@/components/backend-down-banner'

type DashboardViewMode =
  | { view: 'list' }
  | { view: 'detail'; workoutId: number; fingerprint?: string }

const PANEL_KEYS = [
  'summary',
  'workouts',
  'volume',
  'steps',
  'heart',
  'sleep',
  'sleepStages',
  'capabilities',
  'datasetStatus',
] as const
type PanelKey = (typeof PANEL_KEYS)[number]

const PANEL_LABELS: Record<PanelKey, string> = {
  summary: 'activity rings',
  workouts: 'workouts',
  volume: 'training volume',
  steps: 'steps',
  heart: 'heart rate',
  sleep: 'sleep',
  sleepStages: 'sleep stages',
  capabilities: 'data sources',
  datasetStatus: 'import status',
}

function createLoadingPanels(value: boolean): Record<PanelKey, boolean> {
  return Object.fromEntries(PANEL_KEYS.map((key) => [key, value])) as Record<PanelKey, boolean>
}

interface DashboardState {
  summary: ActivityRingDay[]
  workouts: WorkoutSummary[]
  volume: TrainingVolumeResponse | null
  steps: TrendResponse | null
  heart: TrendResponse | null
  sleep: TrendResponse | null
  sleepStages: SleepStagesResponse | null
  capabilities: CapabilityFlag[]
  datasetStatus: DatasetStatus | null
  nextWorkoutCursor: string | null
  loadingPanels: Record<PanelKey, boolean>
  failedPanels: string[]
}

function NoData() {
  return <p className="text-sm text-gray-400 py-4">No data</p>
}

function PanelSkeleton({ panel }: { panel: PanelKey }) {
  return (
    <div
      className="h-16 animate-pulse rounded bg-gray-100 py-5 text-center text-sm text-gray-400"
      data-testid={`panel-loading-${panel}`}
      role="status"
    >
      Loading {PANEL_LABELS[panel]}…
    </div>
  )
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
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

/** Memoized workout table row: skips re-render when the workout and handler are unchanged. */
const WorkoutRow = memo(function WorkoutRow({
  workout,
  onSelect,
}: {
  workout: WorkoutSummary
  onSelect: (workout: WorkoutSummary) => void
}) {
  const w = workout
  return (
    <tr
      onClick={() => onSelect(w)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(w)
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
        {w.distance_meters !== null ? `${formatNumber(w.distance_meters / 1000, 1)} km` : '—'}
      </td>
      <td className="whitespace-nowrap px-3 py-3 text-right tabular-nums">
        {w.energy_burned_kj !== null ? `${formatNumber(w.energy_burned_kj, 0)} kJ` : '—'}
      </td>
    </tr>
  )
})

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
  onSelect: (workout: WorkoutSummary) => void
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
  // Single-pass per-type counts (O(N)) instead of filtering per type per render.
  const workoutCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const workout of workouts) {
      counts.set(workout.activity_type, (counts.get(workout.activity_type) ?? 0) + 1)
    }
    return counts
  }, [workouts])
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
          const count = workoutCounts.get(type) ?? 0
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
              <WorkoutRow key={w.id} workout={w} onSelect={onSelect} />
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

function TrainingVolumePanel({
  volume,
  granularity,
  onGranularityChange,
}: {
  volume: TrainingVolumeResponse | null
  granularity: 'week' | 'month'
  onGranularityChange: (value: 'week' | 'month') => void
}) {
  if (!volume || volume.series.length === 0) return <NoData />
  const totals = volume.totals
  const durationSeries = volume.series.map((item) => ({
    bucket: item.bucket,
    value: item.duration_minutes,
  }))
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 text-xs text-gray-500">
        <span>Aggregate by</span>
        <div
          className="flex rounded border border-gray-200 bg-white"
          role="group"
          aria-label="Training volume granularity"
        >
          {(['week', 'month'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={granularity === option}
              onClick={() => onGranularityChange(option)}
              className={`px-2 py-1 capitalize ${granularity === option ? 'bg-blue-50 font-medium text-blue-700' : 'text-gray-600'}`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <SummaryMetric label="Sessions" value={formatNumber(totals.sessions)} />
        <SummaryMetric
          label="Duration"
          value={`${formatNumber(totals.duration_minutes / 60, 1)} h`}
        />
        <SummaryMetric
          label="Distance"
          value={`${formatNumber(totals.distance_meters / 1000, 1)} km`}
        />
        <SummaryMetric label="Energy" value={`${formatNumber(totals.energy_kj, 0)} kJ`} />
      </div>
      <TrendLine
        series={durationSeries}
        metricLabel="Duration"
        metricUnit="minutes"
        title={`Duration per ${volume.granularity}`}
      />
      {volume.by_activity.length > 0 ? (
        <div className="overflow-x-auto rounded-md border border-gray-100">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Training volume by activity</caption>
            <thead className="border-b bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Activity</th>
                <th className="px-3 py-2 text-right">Sessions</th>
                <th className="px-3 py-2 text-right">Duration</th>
                <th className="px-3 py-2 text-right">Distance</th>
              </tr>
            </thead>
            <tbody>
              {volume.by_activity.map((item) => (
                <tr key={item.activity_type} className="border-b last:border-0">
                  <td className="px-3 py-2 font-medium text-gray-800">
                    {displayActivityType(item.activity_type)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{item.sessions}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatNumber(item.duration_minutes / 60, 1)} h
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatNumber(item.distance_meters / 1000, 1)} km
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-gray-50 p-3">
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 font-semibold tabular-nums text-gray-900">{value}</p>
    </div>
  )
}

function CapabilitiesPanel({ caps }: { caps: CapabilityFlag[] }) {
  if (caps.length === 0) return <NoData />
  return (
    <div className="flex flex-wrap gap-2">
      {caps.map((c) => {
        const state = c.state ?? (c.present ? 'available' : 'unavailable')
        return (
          <span
            key={c.name}
            className={`px-2 py-1 rounded text-xs font-medium ${
              state === 'available'
                ? 'bg-green-100 text-green-800'
                : state === 'out_of_range'
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-gray-100 text-gray-500'
            }`}
          >
            {c.name.replaceAll('_', ' ')} {state === 'available' ? '✓' : state.replaceAll('_', ' ')}
          </span>
        )
      })}
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
export function DashboardView() {
  const initialQuery = decodeDashboardQuery(window.location.search)
  const [state, setState] = useState<DashboardState>({
    summary: [],
    workouts: [],
    volume: null,
    steps: null,
    heart: null,
    sleep: null,
    sleepStages: null,
    capabilities: [],
    datasetStatus: null,
    nextWorkoutCursor: null,
    loadingPanels: createLoadingPanels(true),
    failedPanels: [],
  })
  const [mode, setMode] = useState<DashboardViewMode>(() =>
    initialQuery.selectedWorkout
      ? {
          view: 'detail',
          workoutId: initialQuery.selectedWorkout,
          ...(initialQuery.selectedWorkoutFingerprint
            ? { fingerprint: initialQuery.selectedWorkoutFingerprint }
            : {}),
        }
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
  const backendDown = useBackendHealth()
  const [savedViews, setSavedViews] = useState<SavedView[]>([])
  const [savedViewTitle, setSavedViewTitle] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [volumeGranularity, setVolumeGranularity] = useState<'week' | 'month'>('week')
  const scopeGeneration = useRef(0)
  const paginationController = useRef<AbortController | null>(null)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)

  const reloadSavedViews = () => {
    listSavedViews()
      .then(setSavedViews)
      .catch(() => setSavedViews([]))
  }

  // Health check on mount (R1-12) is shared with the chat view via
  // useBackendHealth.

  useEffect(() => {
    reloadSavedViews()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const generation = scopeGeneration.current + 1
    scopeGeneration.current = generation

    setState((current) => ({
      ...current,
      loadingPanels: createLoadingPanels(true),
      failedPanels: [],
    }))

    const isCurrent = () => active && scopeGeneration.current === generation
    const loadPanel = <T,>(
      panel: PanelKey,
      request: Promise<T>,
      apply: (current: DashboardState, value: T) => Partial<DashboardState>,
    ) => {
      void request.then(
        (value) => {
          if (!isCurrent()) return
          setState((current) => ({
            ...current,
            ...apply(current, value),
            loadingPanels: { ...current.loadingPanels, [panel]: false },
            failedPanels: current.failedPanels.filter((label) => label !== PANEL_LABELS[panel]),
          }))
        },
        (error: unknown) => {
          if (!isCurrent() || isAbortError(error)) return
          const label = PANEL_LABELS[panel]
          setState((current) => ({
            ...current,
            loadingPanels: { ...current.loadingPanels, [panel]: false },
            failedPanels: current.failedPanels.includes(label)
              ? current.failedPanels
              : [...current.failedPanels, label],
          }))
        },
      )
    }

    loadPanel('summary', fetchSummary(scope, controller.signal), (_current, value) => ({
      summary: value,
    }))
    loadPanel(
      'workouts',
      fetchWorkouts(scope, undefined, controller.signal),
      (_current, value) => ({
        workouts: value.workouts,
        nextWorkoutCursor: value.next_cursor,
      }),
    )
    loadPanel(
      'volume',
      fetchTrainingVolume(scope, volumeGranularity, controller.signal),
      (_current, value) => ({ volume: value }),
    )
    loadPanel('steps', fetchTrend('steps', 'day', scope, controller.signal), (_current, value) => ({
      steps: value,
    }))
    loadPanel(
      'heart',
      fetchTrend('heart', 'week', scope, controller.signal),
      (_current, value) => ({
        heart: value,
      }),
    )
    loadPanel('sleep', fetchTrend('sleep', 'day', scope, controller.signal), (_current, value) => ({
      sleep: value,
    }))
    loadPanel('sleepStages', fetchSleepStages(scope, controller.signal), (_current, value) => ({
      sleepStages: value,
    }))
    loadPanel('capabilities', fetchCapabilities(scope, controller.signal), (_current, value) => ({
      capabilities: value,
    }))
    loadPanel('datasetStatus', fetchDatasetStatus(controller.signal), (_current, value) => ({
      datasetStatus: value,
    }))

    return () => {
      active = false
      controller.abort()
      paginationController.current?.abort()
      paginationController.current = null
    }
  }, [scope, reloadToken, volumeGranularity])

  const loadMoreWorkouts = () => {
    if (!state.nextWorkoutCursor) return
    paginationController.current?.abort()
    const controller = new AbortController()
    paginationController.current = controller
    const generation = scopeGeneration.current
    setLoadMoreError(null)
    fetchWorkouts(scope, state.nextWorkoutCursor, controller.signal)
      .then((page) => {
        if (scopeGeneration.current !== generation || controller.signal.aborted) return
        setState((current) => ({
          ...current,
          workouts: [...current.workouts, ...page.workouts],
          nextWorkoutCursor: page.next_cursor,
        }))
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        if (scopeGeneration.current === generation) {
          setLoadMoreError(error instanceof Error ? error.message : 'Could not load more workouts.')
        }
      })
      .finally(() => {
        if (paginationController.current === controller) paginationController.current = null
      })
  }

  const updateWorkoutScope = (nextScope: DashboardScope) => {
    const normalized: DashboardScope = {
      ...(nextScope.start ? { start: nextScope.start } : {}),
      ...(nextScope.end ? { end: nextScope.end } : {}),
      ...(nextScope.activityType ? { activityType: nextScope.activityType } : {}),
      ...(nextScope.source ? { source: nextScope.source } : {}),
    }
    // Build the URL from the fresh scope instead of merging over the previous
    // query string: collapsing scope (e.g. resetting source to "All sources")
    // must not leave stale filter params like `source=…` in the URL. Preserve
    // only non-filter URL state such as the selected workout detail.
    const query = decodeDashboardQuery(window.location.search)
    window.history.pushState(
      {},
      '',
      `?${encodeDashboardQuery({
        tab: 'workouts',
        ...normalized,
        ...(query.selectedWorkout ? { selectedWorkout: query.selectedWorkout } : {}),
        ...(query.selectedWorkoutFingerprint
          ? { selectedWorkoutFingerprint: query.selectedWorkoutFingerprint }
          : {}),
      })}`,
    )
    setScope(normalized)
  }

  const selectWorkout = useCallback((workout: WorkoutSummary) => {
    const query = decodeDashboardQuery(window.location.search)
    window.history.pushState(
      {},
      '',
      `?${encodeDashboardQuery({
        ...query,
        tab: 'workouts',
        selectedWorkout: workout.id,
        selectedWorkoutFingerprint: workout.fingerprint,
      })}`,
    )
    setMode({ view: 'detail', workoutId: workout.id, fingerprint: workout.fingerprint })
  }, [])

  const returnToWorkoutList = () => {
    const {
      selectedWorkout: _selectedWorkout,
      selectedWorkoutFingerprint: _selectedWorkoutFingerprint,
      ...query
    } = decodeDashboardQuery(window.location.search)
    window.history.pushState({}, '', `?${encodeDashboardQuery(query)}`)
    setMode({ view: 'list' })
  }

  const applySavedView = (query: DashboardQuery) => {
    const nextScope: DashboardScope = {
      ...(query.start && query.end ? { start: query.start, end: query.end } : {}),
      ...(query.activityType ? { activityType: query.activityType } : {}),
      ...(query.source ? { source: query.source } : {}),
    }
    const nextQuery = { ...query, tab: query.tab }
    window.history.pushState({}, '', `?${encodeDashboardQuery(nextQuery)}`)
    setMode(
      nextQuery.selectedWorkout
        ? {
            view: 'detail',
            workoutId: nextQuery.selectedWorkout,
            ...(nextQuery.selectedWorkoutFingerprint
              ? { fingerprint: nextQuery.selectedWorkoutFingerprint }
              : {}),
          }
        : { view: 'list' },
    )
    setScope(nextScope)
  }

  const saveCurrentView = () => {
    if (!scope.start || !scope.end) return
    const title = savedViewTitle.trim()
    if (!title) {
      setSaveError('Enter a name for this view.')
      return
    }
    setSaveError(null)
    createSavedView(title, { tab: 'overview', ...scope })
      .then(() => {
        setSavedViewTitle('')
        reloadSavedViews()
      })
      .catch((error: unknown) =>
        setSaveError(error instanceof Error ? error.message : 'Could not save this view.'),
      )
  }

  // Workout detail view (R1-09)
  if (mode.view === 'detail') {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <WorkoutDetail
          workoutId={mode.workoutId}
          {...(mode.fingerprint ? { fingerprint: mode.fingerprint } : {})}
          onBack={returnToWorkoutList}
        />
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
          {saveError ? <p className="text-xs text-red-600">{saveError}</p> : null}
        </div>
      ) : null}

      <Section title="Activity Rings (Latest available day)">
        {state.loadingPanels.summary && state.summary.length === 0 ? (
          <PanelSkeleton panel="summary" />
        ) : (
          <ActivityRingsPanel days={state.summary} />
        )}
      </Section>

      <Section title="Recent Workouts (Latest 30 data days)">
        {state.loadingPanels.workouts && state.workouts.length === 0 ? (
          <PanelSkeleton panel="workouts" />
        ) : (
          <WorkoutsPanel
            workouts={state.workouts}
            nextWorkoutCursor={state.nextWorkoutCursor}
            scope={scope}
            onScopeChange={updateWorkoutScope}
            onSelect={selectWorkout}
            onLoadMore={loadMoreWorkouts}
          />
        )}
        {loadMoreError ? <p className="mt-2 text-sm text-red-600">{loadMoreError}</p> : null}
      </Section>

      <Section title="Training Volume (Latest 90 data days)">
        {state.loadingPanels.volume && state.volume === null ? (
          <PanelSkeleton panel="volume" />
        ) : (
          <TrainingVolumePanel
            volume={state.volume}
            granularity={volumeGranularity}
            onGranularityChange={setVolumeGranularity}
          />
        )}
      </Section>

      <Section title="Daily Steps (Latest 30 data days)">
        {state.loadingPanels.steps && state.steps === null ? (
          <PanelSkeleton panel="steps" />
        ) : (
          <TrendPanel trend={state.steps} title="Steps" />
        )}
      </Section>

      <Section title="Resting Heart Rate (Latest 90 data days)">
        {state.loadingPanels.heart && state.heart === null ? (
          <PanelSkeleton panel="heart" />
        ) : (
          <TrendPanel trend={state.heart} title="Resting HR" />
        )}
      </Section>

      <Section title="Sleep Duration (Latest 30 data days)">
        {state.loadingPanels.sleep && state.sleep === null ? (
          <PanelSkeleton panel="sleep" />
        ) : (
          <TrendPanel trend={state.sleep} title="Sleep" />
        )}
      </Section>

      <Section title="Measured Sleep Stages">
        {state.loadingPanels.sleepStages && state.sleepStages === null ? (
          <PanelSkeleton panel="sleepStages" />
        ) : (
          <SleepStagesPanel stages={state.sleepStages} />
        )}
      </Section>

      <Section title="Data Sources">
        {state.loadingPanels.capabilities && state.capabilities.length === 0 ? (
          <PanelSkeleton panel="capabilities" />
        ) : (
          <CapabilitiesPanel caps={state.capabilities} />
        )}
      </Section>
    </div>
  )
}
