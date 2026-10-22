import { memo } from 'react'
import type { TrendChartData } from '@/types/templates'
import { LazyTrendLine as TrendLine } from '@/charts/lazy-trend-line'

interface TrendChartProps {
  data: TrendChartData
  narrative?: string
}

/** Renders a metric trend over time as a line chart. */
export const TrendChart = memo(function TrendChart({ data, narrative }: TrendChartProps) {
  if (data.series.length === 0 || data.series.every((point) => point.value === null)) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="font-bold text-gray-900">{data.title}</h2>
        {narrative ? <p className="mt-2 text-gray-600">{narrative}</p> : null}
        <p className="mt-2 text-gray-500">No trend data available. Try a wider date range.</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      {narrative ? <p className="mb-4 text-gray-600">{narrative}</p> : null}
      <TrendLine
        series={data.series}
        metricLabel={data.metric_label}
        metricUnit={data.metric_unit}
        title={data.title}
      />
    </div>
  )
})
