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

async function checkedFetch(url: string): Promise<Response> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Dashboard request failed: ${r.status} ${r.statusText}`)
  return r
}

export async function fetchSummary(): Promise<ActivityRingDay[]> {
  const r = await checkedFetch('/api/dashboard/summary')
  const d = (await r.json()) as { days: ActivityRingDay[] }
  return d.days
}

export async function fetchWorkouts(): Promise<WorkoutSummary[]> {
  const r = await checkedFetch('/api/dashboard/workouts')
  const d = (await r.json()) as { workouts: WorkoutSummary[] }
  return d.workouts
}

export async function fetchTrend(
  endpoint: 'steps' | 'heart' | 'sleep',
  granularity = 'day',
): Promise<TrendResponse> {
  const r = await checkedFetch(`/api/dashboard/${endpoint}?granularity=${granularity}`)
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
