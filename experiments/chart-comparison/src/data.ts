// Typed access to the gitignored chart_data.json (derived from private health data).
import raw from '../chart_data.json'

export interface DatePoint { date: string; value: number }
export interface StepPoint { date: string; steps: number }
export interface Workout {
  date: string
  type: string
  durationMin: number
  avgHr: number | null
  distanceKm: number | null
}
export interface SportCount { type: string; count: number }
export interface WeeklyVolumeRow { week: string; [sport: string]: number | string }
export interface ActivityRings {
  date: string
  move: number; moveGoal: number
  exercise: number; exerciseGoal: number
  stand: number; standGoal: number
}

export interface ChartData {
  meta: { generated: string; source: string; range: string; topSports: string[] }
  restingHrDaily: DatePoint[]
  stepsDaily: StepPoint[]
  hrvDaily: DatePoint[]
  workouts: Workout[]
  sportBreakdown: SportCount[]
  weeklyVolumeBySport: WeeklyVolumeRow[]
  activityRings: ActivityRings
}

const data = raw as unknown as ChartData
export default data

// shared light-mode palette used across all libraries
export const PALETTE = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#06b6d4', // cyan
]

// short label for dates on axes
export const shortDate = (iso: string) => iso.slice(5) // MM-DD

// the sports tracked in the stacked weekly volume chart
export const TOP_SPORTS = data.meta.topSports
