import { memo, useMemo } from 'react'
import { Doughnut } from 'react-chartjs-2'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'

ChartJS.register(ArcElement, Tooltip, Legend)

interface GaugeRingsProps {
  energy: { current: number | null; goal: number | null }
  exercise: { current: number | null; goal: number | null }
  stand: { current: number | null; goal: number | null }
}

/** Static Chart.js options: hoisted so every render reuses one identity. */
const RING_OPTIONS = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: { display: false },
    tooltip: { enabled: false },
  },
}

const RING_TRACK_COLOR = '#f3f4f6'

function ringDataset(label: string, pct: number, color: string, cutout: string) {
  return {
    label,
    data: [pct, 100 - pct],
    backgroundColor: [color, RING_TRACK_COLOR],
    borderWidth: 0,
    circumference: 270,
    rotation: 225,
    cutout,
  }
}

/** Concentric doughnut chart rendering Apple Fitness-style activity rings (R1-04).
 * Memoized on the six ring primitives so fresh parent object literals don't
 * force a Chart.js re-render. */
export const GaugeRings = memo(function GaugeRings({ energy, exercise, stand }: GaugeRingsProps) {
  const { current: energyCurrent, goal: energyGoal } = energy
  const { current: exerciseCurrent, goal: exerciseGoal } = exercise
  const { current: standCurrent, goal: standGoal } = stand
  const data = useMemo(() => {
    const energyPct = getPct({ current: energyCurrent, goal: energyGoal })
    const exercisePct = getPct({ current: exerciseCurrent, goal: exerciseGoal })
    const standPct = getPct({ current: standCurrent, goal: standGoal })
    return {
      labels: ['Energy (kJ)', 'Exercise (min)', 'Stand (hrs)'],
      datasets: [
        ringDataset('Energy', energyPct, '#ef4444', '75%'),
        ringDataset('Exercise', exercisePct, '#22c55e', '60%'),
        ringDataset('Stand', standPct, '#3b82f6', '45%'),
      ],
    }
  }, [energyCurrent, energyGoal, exerciseCurrent, exerciseGoal, standCurrent, standGoal])

  return (
    <div className="mx-auto max-w-[200px]">
      <Doughnut data={data} options={RING_OPTIONS} />
      <div className="mt-2 flex justify-center gap-4 text-xs">
        <RingLabel color="#ef4444" label="Energy" value={fmtValue(energy)} />
        <RingLabel color="#22c55e" label="Exercise" value={fmtValue(exercise)} />
        <RingLabel color="#3b82f6" label="Stand" value={fmtValue(stand)} />
      </div>
    </div>
  )
})

function RingLabel({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="text-center">
      <span className="block text-gray-500">{label}</span>
      <span className="block font-semibold" style={{ color }}>
        {value}
      </span>
    </div>
  )
}

function getPct(ring: { current: number | null; goal: number | null }): number {
  if (ring.current === null || ring.goal === null || ring.goal === 0) return 0
  return Math.min(100, Math.round((ring.current / ring.goal) * 100))
}

function fmtValue(ring: { current: number | null; goal: number | null }): string {
  const c = ring.current !== null ? Math.round(ring.current) : 0
  const g = ring.goal !== null ? Math.round(ring.goal) : 0
  return `${c} / ${g}`
}
