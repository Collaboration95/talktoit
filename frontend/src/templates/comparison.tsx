import type { ComparisonData, ComparisonMetric } from '@/types/templates'

interface ComparisonProps {
  data: ComparisonData
  narrative?: string
}

/** Renders a period-vs-period comparison table. */
export function Comparison({ data, narrative }: ComparisonProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {narrative ? <p className="mb-4 text-gray-600">{narrative}</p> : null}
      <h2 className="mb-1 font-bold text-gray-900">{data.title}</h2>
      <div className="mb-4 flex gap-4 text-sm text-gray-500">
        <span>{data.this_period_label}</span>
        <span>vs</span>
        <span>{data.last_period_label}</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2 pr-4 font-medium">Metric</th>
            <th className="py-2 pr-4 font-medium">{data.this_period_label}</th>
            <th className="py-2 pr-4 font-medium">{data.last_period_label}</th>
            <th className="py-2 font-medium">Change</th>
          </tr>
        </thead>
        <tbody>
          {data.metrics.map((m) => (
            <ComparisonRow key={m.label} metric={m} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function directionArrow(direction: ComparisonMetric['direction']): string {
  if (direction === 'up') return '↑'
  if (direction === 'down') return '↓'
  return '→'
}

function directionColor(direction: ComparisonMetric['direction']): string {
  if (direction === 'up') return 'text-green-600'
  if (direction === 'down') return 'text-red-600'
  return 'text-gray-500'
}

function ComparisonRow({ metric }: { metric: ComparisonMetric }) {
  const arrow = directionArrow(metric.direction)
  const color = directionColor(metric.direction)
  const deltaStr =
    metric.delta !== null ? `${metric.delta > 0 ? '+' : ''}${metric.delta.toFixed(1)}` : '—'
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-4 font-medium text-gray-700">{metric.label}</td>
      <td className="py-2 pr-4 text-gray-900">
        {metric.this_value !== null ? `${metric.this_value} ${metric.unit}` : '—'}
      </td>
      <td className="py-2 pr-4 text-gray-500">
        {metric.last_value !== null ? `${metric.last_value} ${metric.unit}` : '—'}
      </td>
      <td className={`py-2 font-medium ${color}`}>
        {arrow} {deltaStr} {metric.unit}
      </td>
    </tr>
  )
}
