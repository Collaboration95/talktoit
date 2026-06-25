import type { PeriodSummaryData } from '@/types/templates'

interface PeriodSummaryProps {
  data: PeriodSummaryData
  narrative?: string
}

/** Renders aggregate metrics for a training period. */
export function PeriodSummary({ data, narrative }: PeriodSummaryProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {narrative ? <p className="mb-4 text-gray-600">{narrative}</p> : null}
      <h2 className="font-bold text-gray-900">{data.title}</h2>
      <p className="mb-4 text-sm text-gray-500">
        {data.period_start} – {data.period_end}
      </p>
      {data.metrics.length === 0 ? (
        <p className="text-gray-500">No data available for this period.</p>
      ) : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {data.metrics.map((m) => (
          <div key={m.label} className="rounded-lg bg-gray-50 p-3">
            <p className="text-xs text-gray-500">{m.label}</p>
            <p className="mt-1 font-semibold text-gray-900">
              {m.value !== null ? `${m.value} ${m.unit}` : '—'}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
