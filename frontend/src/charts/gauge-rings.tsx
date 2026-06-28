import { Doughnut } from 'react-chartjs-2'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'

ChartJS.register(ArcElement, Tooltip, Legend)

interface GaugeRingsProps {
  energy: { current: number | null; goal: number | null }
  exercise: { current: number | null; goal: number | null }
  stand: { current: number | null; goal: number | null }
}

/** Concentric doughnut chart rendering Apple Fitness-style activity rings (R1-04). */
export function GaugeRings({ energy, exercise, stand }: GaugeRingsProps) {
  const energyPct = getPct(energy)
  const exercisePct = getPct(exercise)
  const standPct = getPct(stand)

  const data = {
    labels: ['Energy (kJ)', 'Exercise (min)', 'Stand (hrs)'],
    datasets: [
      {
        label: 'Energy',
        data: [energyPct, 100 - energyPct],
        backgroundColor: ['#ef4444', '#f3f4f6'],
        borderWidth: 0,
        circumference: 270,
        rotation: 225,
        cutout: '75%',
      },
      {
        label: 'Exercise',
        data: [exercisePct, 100 - exercisePct],
        backgroundColor: ['#22c55e', '#f3f4f6'],
        borderWidth: 0,
        circumference: 270,
        rotation: 225,
        cutout: '60%',
      },
      {
        label: 'Stand',
        data: [standPct, 100 - standPct],
        backgroundColor: ['#3b82f6', '#f3f4f6'],
        borderWidth: 0,
        circumference: 270,
        rotation: 225,
        cutout: '45%',
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false },
    },
  }

  return (
    <div className="mx-auto max-w-[200px]">
      <Doughnut data={data} options={options} />
      <div className="mt-2 flex justify-center gap-4 text-xs">
        <RingLabel color="#ef4444" label="Energy" value={fmtValue(energy)} />
        <RingLabel color="#22c55e" label="Exercise" value={fmtValue(exercise)} />
        <RingLabel color="#3b82f6" label="Stand" value={fmtValue(stand)} />
      </div>
    </div>
  )
}

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
