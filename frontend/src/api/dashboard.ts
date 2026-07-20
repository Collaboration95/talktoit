export interface ActivityRingDay {
  date: string
  energy_kj: number | null
  energy_goal_kj: number | null
  exercise_min: number | null
  exercise_goal_min: number | null
  stand_hours: number | null
  stand_goal_hours: number | null
}

export interface WorkoutSummary {
  id: number
  activity_type: string
  date: string
  duration_minutes: number | null
  avg_heart_rate: number | null
  distance_meters: number | null
  energy_burned_kj: number | null
  source_name: string
  fingerprint: string
}

export interface TrendPoint {
  bucket: string
  value: number | null
}

export interface TrendResponse {
  metric_label: string
  metric_unit: string
  granularity: string
  series: TrendPoint[]
}

export interface SleepStagesResponse {
  total_asleep_hours: number
  stages_hours: Record<string, number>
  stage_data_available: boolean
  message: string
}

export interface CapabilityFlag {
  name: string
  present: boolean
  state: 'available' | 'unavailable' | 'out_of_range'
}

export interface DatasetStatus {
  readiness: 'ready' | 'no_active_import'
  dataset: { coverage_start: string | null; coverage_end: string | null } | null
}

export interface DashboardScope {
  start?: string
  end?: string
  activityType?: string
  source?: string
}

export interface WorkoutsPage {
  workouts: WorkoutSummary[]
  next_cursor: string | null
}

// R1-01: Workout detail types
export interface GpsRoute {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface KeyValuePair {
  key: string
  value: string
}

export interface WorkoutDetail {
  id: number
  activity_type: string
  date: string
  duration_minutes: number | null
  avg_heart_rate: number | null
  max_heart_rate: number | null
  distance_meters: number | null
  distance_unit: 'km' | 'm'
  energy_burned_kj: number | null
  elevation_ascent_meters: number | null
  source_name: string
  gps_route: GpsRoute | null
  metadata: KeyValuePair[]
}

function withScope(path: string, scope: DashboardScope = {}): string {
  const params = new URLSearchParams()
  if (scope.start) params.set('start', scope.start)
  if (scope.end) params.set('end', scope.end)
  if (scope.activityType) params.set('activity_type', scope.activityType)
  if (scope.source) params.set('source', scope.source)
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

async function checkedFetch(url: string, signal?: AbortSignal): Promise<Response> {
  const r = await fetch(url, signal ? { signal } : undefined)
  if (!r.ok) throw new Error(`Dashboard request failed: ${r.status} ${r.statusText}`)
  return r
}

export async function fetchSummary(
  scope?: DashboardScope,
  signal?: AbortSignal,
): Promise<ActivityRingDay[]> {
  const r = await checkedFetch(withScope('/api/dashboard/summary', scope), signal)
  const d = (await r.json()) as { days: ActivityRingDay[] }
  return d.days
}

export async function fetchWorkouts(
  scope?: DashboardScope,
  cursor?: string,
  signal?: AbortSignal,
): Promise<WorkoutsPage> {
  const params = new URLSearchParams()
  if (cursor) params.set('cursor', cursor)
  const suffix = params.toString()
  const path = withScope('/api/dashboard/workouts', scope)
  const url = suffix ? `${path}${path.includes('?') ? '&' : '?'}${suffix}` : path
  const r = await checkedFetch(url, signal)
  return r.json() as Promise<WorkoutsPage>
}

export async function fetchTrend(
  endpoint: 'steps' | 'heart' | 'sleep',
  granularity = 'day',
  scope?: DashboardScope,
  signal?: AbortSignal,
): Promise<TrendResponse> {
  const scoped = withScope(`/api/dashboard/${endpoint}`, scope)
  const separator = scoped.includes('?') ? '&' : '?'
  const r = await checkedFetch(`${scoped}${separator}granularity=${granularity}`, signal)
  return r.json() as Promise<TrendResponse>
}

export async function fetchSleepStages(
  scope?: DashboardScope,
  signal?: AbortSignal,
): Promise<SleepStagesResponse> {
  const r = await checkedFetch(withScope('/api/dashboard/sleep/stages', scope), signal)
  return r.json() as Promise<SleepStagesResponse>
}

export async function fetchCapabilities(
  scope?: DashboardScope,
  signal?: AbortSignal,
): Promise<CapabilityFlag[]> {
  const r = await checkedFetch(withScope('/api/dashboard/capabilities', scope), signal)
  const d = (await r.json()) as { capabilities: CapabilityFlag[] }
  return d.capabilities
}

export async function fetchDatasetStatus(signal?: AbortSignal): Promise<DatasetStatus> {
  const r = await checkedFetch('/api/status', signal)
  return r.json() as Promise<DatasetStatus>
}

/** Fetch full detail for a single workout (R1-01). */
export async function fetchWorkoutDetail(id: number): Promise<WorkoutDetail> {
  const r = await checkedFetch(`/api/dashboard/workouts/${id}`)
  return r.json() as Promise<WorkoutDetail>
}
