// Tremor chart components — individual exports for type-first gallery
import { AreaChart, BarChart, DonutChart, BarList } from '@tremor/react'
import data, { TOP_SPORTS } from '../data'

const tremorColors = ['blue', 'emerald', 'amber', 'rose', 'violet', 'cyan'] as const

const hrData = data.restingHrDaily.map(d => ({ date: d.date.slice(5), 'Resting HR': d.value }))

const weeklySteps = buildWeeklySteps()
const stepsData = weeklySteps.map(w => ({ week: w.week, Steps: w.steps }))

const stackData = data.weeklyVolumeBySport.map(w => {
  const row: Record<string, string | number> = { week: w.week.slice(5) }
  TOP_SPORTS.forEach(s => { row[s] = (w[s] as number) || 0 })
  return row
})

const sportData = data.sportBreakdown.map(s => ({ name: s.type, value: s.count }))

const rings = data.activityRings
export const ringBarList = [
  { name: `Move  (${rings.move} / ${rings.moveGoal} cal)`, value: Math.round((rings.move / rings.moveGoal) * 100) },
  { name: `Exercise  (${rings.exercise} / ${rings.exerciseGoal} min)`, value: Math.round((rings.exercise / rings.exerciseGoal) * 100) },
  { name: `Stand  (${rings.stand} / ${rings.standGoal} hrs)`, value: Math.round((rings.stand / rings.standGoal) * 100) },
]

export const topWorkoutsByHr = [...data.workouts]
  .filter(w => w.avgHr)
  .sort((a, b) => (b.avgHr ?? 0) - (a.avgHr ?? 0))
  .slice(0, 8)
  .map(w => ({ name: `${w.type} · ${w.date.slice(5)}`, value: Math.round(w.avgHr ?? 0) }))

export function TremorArea() {
  return (
    <AreaChart data={hrData} index="date" categories={['Resting HR']}
      colors={['blue']} showLegend={false} showGridLines curveType="monotone" className="h-full" />
  )
}

export function TremorBar() {
  return (
    <BarChart data={stepsData} index="week" categories={['Steps']}
      colors={['blue']} showLegend={false} className="h-full" />
  )
}

export function TremorStacked() {
  return (
    <BarChart
      data={stackData as Record<string, string | number>[]}
      index="week" categories={TOP_SPORTS}
      colors={[...tremorColors]} stack showLegend className="h-full" />
  )
}

export function TremorDonut() {
  return (
    <DonutChart data={sportData} category="value" index="name"
      colors={[...tremorColors]} showLabel className="h-full" />
  )
}

export function TremorBarList() {
  return (
    <div className="overflow-y-auto h-full pt-1">
      <BarList data={topWorkoutsByHr} valueFormatter={(v: number) => `${v} bpm`} color="amber" />
    </div>
  )
}

export function TremorRingList() {
  return (
    <div className="pt-4">
      <BarList data={ringBarList} valueFormatter={(v: number) => `${v}%`} color="emerald" />
    </div>
  )
}

function buildWeeklySteps() {
  const m = new Map<string, number>()
  data.stepsDaily.forEach(d => {
    const dt = new Date(d.date)
    const mon = new Date(dt)
    mon.setDate(dt.getDate() - ((dt.getDay() + 6) % 7))
    const key = mon.toISOString().slice(5, 10)
    m.set(key, (m.get(key) ?? 0) + d.steps)
  })
  return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([week, steps]) => ({ week, steps }))
}
