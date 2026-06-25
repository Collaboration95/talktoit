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

/** Returns a local-timezone ISO date string (YYYY-MM-DD) offset by `offsetDays` days back. */
function localISODate(offsetDays = 0): string {
  const d = new Date()
  d.setDate(d.getDate() - offsetDays)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

async function checkedFetch(url: string): Promise<Response> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Dashboard request failed: ${r.status} ${r.statusText}`)
  return r
}

export async function fetchSummary(days = 7): Promise<ActivityRingDay[]> {
  const end = localISODate(0)
  const start = localISODate(days - 1)
  const r = await checkedFetch(`/api/dashboard/summary?start=${start}&end=${end}`)
  const d = (await r.json()) as { days: ActivityRingDay[] }
  return d.days
}

export async function fetchWorkouts(days = 30): Promise<WorkoutSummary[]> {
  const end = localISODate(0)
  const start = localISODate(days)
  const r = await checkedFetch(`/api/dashboard/workouts?start=${start}&end=${end}`)
  const d = (await r.json()) as { workouts: WorkoutSummary[] }
  return d.workouts
}

export async function fetchTrend(
  endpoint: 'steps' | 'heart' | 'sleep',
  days = 30,
  granularity = 'day',
): Promise<TrendResponse> {
  const end = localISODate(0)
  const start = localISODate(days)
  const r = await checkedFetch(
    `/api/dashboard/${endpoint}?start=${start}&end=${end}&granularity=${granularity}`,
  )
  return r.json() as Promise<TrendResponse>
}

export async function fetchCapabilities(): Promise<CapabilityFlag[]> {
  const r = await checkedFetch('/api/dashboard/capabilities')
  const d = (await r.json()) as { capabilities: CapabilityFlag[] }
  return d.capabilities
}
