import { render, screen } from '@testing-library/react'
import { TrendChart } from '@/templates/trend-chart'
import type { TrendChartData } from '@/types/templates'

// Mock echarts-for-react to avoid canvas setup in jsdom
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: unknown }) => (
    <div data-testid="echarts" data-option={JSON.stringify(option)} />
  ),
}))

const validData: TrendChartData = {
  title: 'Resting HR',
  metric_label: 'Resting HR',
  metric_unit: 'bpm',
  granularity: 'week',
  series: [
    { bucket: '2026-W23', value: 51 },
    { bucket: '2026-W24', value: 48.5 },
  ],
}

describe('TrendChart', () => {
  it('renders the chart when series has data', () => {
    render(<TrendChart data={validData} />)
    expect(screen.getByTestId('echarts')).toBeInTheDocument()
  })

  it('renders empty state when series is empty', () => {
    render(<TrendChart data={{ ...validData, series: [] }} />)
    expect(screen.getByText('No trend data available.')).toBeInTheDocument()
  })

  it('renders narrative when provided', () => {
    render(<TrendChart data={validData} narrative="Steady HR this month." />)
    expect(screen.getByText('Steady HR this month.')).toBeInTheDocument()
  })
})
