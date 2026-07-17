import type { FallbackData } from '@/types/templates'

interface FallbackProps {
  data: FallbackData
  narrative?: string
}

/** Renders a generic fallback for unmatched or unanswerable questions. */
export function Fallback({ data, narrative }: FallbackProps) {
  const hasStructuredContent = data.text !== null || (data.table !== null && data.table.length > 0)
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900">
        {hasStructuredContent ? 'Answer unavailable' : 'Could not answer from your health data'}
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        {narrative ?? 'Try asking about workouts, trends, comparisons, or weekly summaries.'}
      </p>
      {data.text ? <p className="mt-3 text-gray-700">{data.text}</p> : null}
      {data.table !== null && data.table.length > 0 ? (
        <table className="mt-3 w-full text-sm">
          <tbody>
            {data.table.map((row) => (
              <tr key={row.key} className="border-b last:border-0">
                <td className="py-1 pr-4 font-medium text-gray-600">{row.key}</td>
                <td className="py-1 text-gray-700">{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {data.text === null && (data.table === null || data.table.length === 0) ? (
        <p className="mt-3 text-gray-500">
          No answer is available yet. Try rephrasing with a workout type, a date range, or a
          specific metric.
        </p>
      ) : null}
    </div>
  )
}
