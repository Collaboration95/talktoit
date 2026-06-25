import type { FallbackData } from '@/types/templates'

interface FallbackProps {
  data: FallbackData
  narrative?: string
}

/** Renders a generic fallback for unmatched or unanswerable questions. */
export function Fallback({ data, narrative }: FallbackProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <p className="mb-2 text-sm text-gray-400">Question: {data.question}</p>
      {narrative ? <p className="mb-3 text-gray-600">{narrative}</p> : null}
      {data.text ? <p className="text-gray-700">{data.text}</p> : null}
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
        <p className="text-gray-500">No answer available for this question.</p>
      ) : null}
    </div>
  )
}
