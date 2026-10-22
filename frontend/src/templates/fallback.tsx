import type { FallbackData } from '@/types/templates'

interface FallbackProps {
  data: FallbackData
  narrative?: string
}

/** Renders a generic fallback for unmatched or unanswerable questions. */
export function Fallback({ data, narrative }: FallbackProps) {
  const headings = {
    unsupported: 'Not supported yet',
    no_matching_data: 'No matching measurements',
    clarification_needed: 'A little more detail needed',
    provider_unavailable: 'Question provider unavailable',
    unavailable: 'Answer unavailable',
  }
  const hasStructuredContent = data.text !== null || (data.table !== null && data.table.length > 0)
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900">
        {data.reason
          ? headings[data.reason]
          : hasStructuredContent
            ? 'Here is what I found'
            : 'Answer unavailable'}
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        {narrative?.trim() ||
          'Try a specific workout, supported metric trend, or training summary.'}
      </p>
      {data.text ? <p className="mt-3 text-gray-700">{data.text}</p> : null}
      {data.message ? <p className="mt-3 text-gray-700">{data.message}</p> : null}
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
