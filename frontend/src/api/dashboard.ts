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

export async function fetchSummary(days = 7): Promise<ActivityRingDay[]> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - (days - 1) * 86400000).toISOString().slice(0, 10)
  const r = await fetch(`/api/dashboard/summary?start=${start}&end=${end}`)
  const d = (await r.json()) as { days: ActivityRingDay[] }
  return d.days
}

export async function fetchWorkouts(days = 30): Promise<WorkoutSummary[]> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
  const r = await fetch(`/api/dashboard/workouts?start=${start}&end=${end}`)
  const d = (await r.json()) as { workouts: WorkoutSummary[] }
  return d.workouts
}

export async function fetchTrend(
  endpoint: 'steps' | 'heart' | 'sleep',
  days = 30,
  granularity = 'day',
): Promise<TrendResponse> {
  const end = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - days * 86400000).toISOString().slice(0, 10)
  const r = await fetch(
    `/api/dashboard/${endpoint}?start=${start}&end=${end}&granularity=${granularity}`,
  )
  return r.json() as Promise<TrendResponse>
}

export async function fetchCapabilities(): Promise<CapabilityFlag[]> {
  const r = await fetch('/api/dashboard/capabilities')
  const d = (await r.json()) as { capabilities: CapabilityFlag[] }
  return d.capabilities
}
