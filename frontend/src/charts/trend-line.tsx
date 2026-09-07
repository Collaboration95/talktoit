import { memo, useMemo } from 'react'
import type { TrendPoint } from '@/types/templates'
import ReactECharts from 'echarts-for-react'
import {
  formatChartBucketFullDate,
  formatBucketLabel,
  formatMetricValue,
  formatNumber,
} from '@/lib/format'

interface TrendLineProps {
  series: TrendPoint[]
  metricLabel: string
  metricUnit: string
  title: string
}

/** ECharts line chart wrapper for trend_chart data. Memoized so parent
 * re-renders (keystrokes, expand toggles) don't rebuild the option tree. */
export const TrendLine = memo(function TrendLine({
  series,
  metricLabel,
  metricUnit,
  title,
}: TrendLineProps) {
  const option = useMemo(() => {
    const buckets = series.map((point) => point.bucket)
    // Ranges spanning multiple calendar years need a year hint to stay unambiguous.
    const includeYear = new Set(buckets.map((bucket) => bucket.slice(0, 4))).size > 1
    return {
      title: { text: title, textStyle: { fontSize: 14 } },
      tooltip: {
        trigger: 'axis',
        formatter: (params: unknown) => {
          const point = Array.isArray(params)
            ? (params[0] as { value?: number | null; axisValue?: string })
            : null
          const value = point?.value ?? null
          const label = point?.axisValue ? formatChartBucketFullDate(point.axisValue) : ''
          return `${label}: ${formatMetricValue(value, metricUnit) ?? '—'}`
        },
      },
      xAxis: {
        type: 'category',
        data: buckets,
        axisLabel: {
          formatter: (value: string) => formatBucketLabel(value, { includeYear }),
        },
      },
      yAxis: {
        type: 'value',
        name: metricUnit,
        axisLabel: {
          formatter: (value: number) => formatNumber(value, metricUnit === 'km' ? 1 : 0),
        },
      },
      series: [
        {
          name: metricLabel,
          type: 'line',
          data: series.map((p) => p.value),
          connectNulls: false,
          areaStyle: {},
        },
      ],
    }
  }, [series, metricLabel, metricUnit, title])
  return <ReactECharts option={option} style={{ height: 300 }} />
})
