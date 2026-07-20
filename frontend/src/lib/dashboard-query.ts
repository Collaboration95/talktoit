export interface DashboardQuery {
  tab: 'overview' | 'workouts'
  start?: string
  end?: string
  activityType?: string
  source?: string
  selectedWorkout?: number
  selectedWorkoutFingerprint?: string
}

const DEFAULT_QUERY: DashboardQuery = { tab: 'overview' }

function validDate(value: string | null): value is string {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value)
}

/** Decode a shareable dashboard URL into a validated, safe scope. */
export function decodeDashboardQuery(search: string): DashboardQuery {
  const params = new URLSearchParams(search)
  const tab = params.get('tab') === 'workouts' ? 'workouts' : DEFAULT_QUERY.tab
  const start = params.get('start')
  const end = params.get('end')
  const selected = Number(params.get('workout'))
  const selectedFingerprint = params.get('workout_fp')
  const activityType = params.get('activity_type')
  const source = params.get('source')
  return {
    tab,
    ...(validDate(start) && validDate(end) && start <= end ? { start, end } : {}),
    ...(activityType && activityType.length <= 160 ? { activityType } : {}),
    ...(source && source.length <= 160 ? { source } : {}),
    ...(Number.isInteger(selected) && selected > 0 ? { selectedWorkout: selected } : {}),
    ...(selectedFingerprint && /^[a-f0-9]{16}$/.test(selectedFingerprint)
      ? { selectedWorkoutFingerprint: selectedFingerprint }
      : {}),
  }
}

/** Encode only validated dashboard state for a stable shareable URL. */
export function encodeDashboardQuery(query: DashboardQuery): string {
  const params = new URLSearchParams({ tab: query.tab })
  if (query.start && query.end) {
    params.set('start', query.start)
    params.set('end', query.end)
  }
  if (query.activityType) params.set('activity_type', query.activityType)
  if (query.source) params.set('source', query.source)
  if (query.selectedWorkout) params.set('workout', String(query.selectedWorkout))
  if (query.selectedWorkoutFingerprint) params.set('workout_fp', query.selectedWorkoutFingerprint)
  return params.toString()
}
