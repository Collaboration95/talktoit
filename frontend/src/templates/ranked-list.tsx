import type { RankedListData } from '@/types/templates'
import { BarListChart } from '@/charts/bar-list'

interface RankedListProps {
  data: RankedListData
  narrative?: string
}

/** Renders an ordered ranked list using Tremor BarList. */
export function RankedList({ data, narrative }: RankedListProps) {
  if (data.rows.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="font-bold text-gray-900">{data.title}</h2>
        <p className="mt-2 text-gray-500">No data available.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {narrative ? <p className="mb-4 text-gray-600">{narrative}</p> : null}
      <h2 className="mb-4 font-bold text-gray-900">{data.title}</h2>
      <BarListChart rows={data.rows} />
    </div>
  )
}
