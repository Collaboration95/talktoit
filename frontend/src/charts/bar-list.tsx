import { BarList } from '@tremor/react'
import type { RankedListRow } from '@/types/templates'

interface BarListChartProps {
  rows: RankedListRow[]
}

/** Tremor BarList wrapper for ranked_list rows. */
export function BarListChart({ rows }: BarListChartProps) {
  const data = rows.map((row) => ({
    name: row.label,
    value: row.value,
  }))
  return <BarList data={data} />
}
