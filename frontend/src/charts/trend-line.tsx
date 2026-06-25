import type { TrendPoint } from '@/types/templates'
import ReactECharts from 'echarts-for-react'

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
    tooltip: { trigger: 'axis', formatter: `{b}: {c} ${metricUnit}` },
    xAxis: { type: 'category', data: series.map((p) => p.bucket) },
    yAxis: { type: 'value', name: metricUnit },
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
