import type { RankedListRow } from '@/types/templates'
import { formatMetricValue } from '@/lib/format'

interface BarListChartProps {
  rows: RankedListRow[]
}

/** Compact ranked list renderer with rounded values and secondary metrics. */
export function BarListChart({ rows }: BarListChartProps) {
  const maxValue = Math.max(...rows.map((row) => Math.abs(row.value)), 1)
  return (
    <ol className="space-y-4">
      {rows.map((row) => {
        const primaryValue = formatMetricValue(row.value, row.unit) ?? '—'
        const secondaryValue =
          row.secondary_value !== undefined && row.secondary_unit !== undefined
            ? formatMetricValue(row.secondary_value, row.secondary_unit)
            : null
        const widthPct = Math.max(8, (Math.abs(row.value) / maxValue) * 100)
        return (
          <li key={row.rank} className="space-y-2">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                  #{row.rank}
                </p>
                <p className="truncate font-medium text-gray-900" title={row.label}>
                  {row.label}
                </p>
                {secondaryValue ? <p className="text-xs text-gray-500">{secondaryValue}</p> : null}
              </div>
              <p className="shrink-0 whitespace-nowrap font-semibold tabular-nums text-gray-900">
                {primaryValue}
              </p>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-blue-500"
                style={{ width: `${widthPct}%` }}
                aria-hidden="true"
              />
            </div>
          </li>
        )
      })}
    </ol>
  )
}
