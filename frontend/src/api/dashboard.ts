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

export interface CapabilityFlag {
  name: string
  present: boolean
}

export interface DashboardScope {
  start?: string
  end?: string
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
  const query = params.toString()
  return query ? `${path}?${query}` : path
}

async function checkedFetch(url: string): Promise<Response> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Dashboard request failed: ${r.status} ${r.statusText}`)
  return r
}

export async function fetchSummary(scope?: DashboardScope): Promise<ActivityRingDay[]> {
  const r = await checkedFetch(withScope('/api/dashboard/summary', scope))
  const d = (await r.json()) as { days: ActivityRingDay[] }
  return d.days
}

export async function fetchWorkouts(scope?: DashboardScope): Promise<WorkoutSummary[]> {
  const r = await checkedFetch(withScope('/api/dashboard/workouts', scope))
  const d = (await r.json()) as { workouts: WorkoutSummary[] }
  return d.workouts
}

export async function fetchTrend(
  endpoint: 'steps' | 'heart' | 'sleep',
  granularity = 'day',
  scope?: DashboardScope,
): Promise<TrendResponse> {
  const scoped = withScope(`/api/dashboard/${endpoint}`, scope)
  const separator = scoped.includes('?') ? '&' : '?'
  const r = await checkedFetch(`${scoped}${separator}granularity=${granularity}`)
  return r.json() as Promise<TrendResponse>
}

export async function fetchCapabilities(): Promise<CapabilityFlag[]> {
  const r = await checkedFetch('/api/dashboard/capabilities')
  const d = (await r.json()) as { capabilities: CapabilityFlag[] }
  return d.capabilities
}

/** Fetch full detail for a single workout (R1-01). */
export async function fetchWorkoutDetail(id: number): Promise<WorkoutDetail> {
  const r = await checkedFetch(`/api/dashboard/workouts/${id}`)
  return r.json() as Promise<WorkoutDetail>
}
