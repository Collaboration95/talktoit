import { memo } from 'react'
import { DeferredChart } from '@/components/deferred-chart'
import { formatChartBucketFullDate, formatMetricValue } from '@/lib/format'
import type { TrendLineProps } from '@/charts/trend-line'

const loadTrendLine = () =>
  import('@/charts/trend-line').then(({ TrendLine }) => ({ default: TrendLine }))

/** Keeps chart dependencies outside the chat entry and retains measured values on failure. */
export const LazyTrendLine = memo(function LazyTrendLine(props: TrendLineProps) {
  return (
    <DeferredChart
      load={loadTrendLine}
      chartProps={props}
      fallback={
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="mb-2 text-left font-medium">{props.title}</caption>
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col">{props.metricLabel}</th>
              </tr>
            </thead>
            <tbody>
              {props.series.map((point) => (
                <tr key={point.bucket}>
                  <th scope="row" className="pr-4 font-normal">
                    {formatChartBucketFullDate(point.bucket)}
                  </th>
                  <td>{formatMetricValue(point.value, props.metricUnit) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    />
  )
})
