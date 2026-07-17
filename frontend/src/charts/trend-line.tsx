import type { TrendPoint } from '@/types/templates'
import ReactECharts from 'echarts-for-react'
import { formatMetricValue, formatNumber } from '@/lib/format'

interface TrendLineProps {
  series: TrendPoint[]
  metricLabel: string
  metricUnit: string
  title: string
}

/** ECharts line chart wrapper for trend_chart data. */
export function TrendLine({ series, metricLabel, metricUnit, title }: TrendLineProps) {
  const option = {
    title: { text: title, textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const point = Array.isArray(params)
          ? (params[0] as { value?: number | null; axisValueLabel?: string })
          : null
        const value = point?.value ?? null
        return `${point?.axisValueLabel ?? ''}: ${formatMetricValue(value, metricUnit) ?? '—'}`
      },
    },
    xAxis: { type: 'category', data: series.map((p) => p.bucket) },
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
  return <ReactECharts option={option} style={{ height: 300 }} />
}
