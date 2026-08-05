import { render, screen } from '@testing-library/react'
import { TrendChart } from '@/templates/trend-chart'
import type { TrendChartData } from '@/types/templates'

const { mockOption } = vi.hoisted(() => ({
  mockOption: { current: null as Record<string, unknown> | null },
}))

// Mock echarts-for-react to avoid canvas setup in jsdom and capture the option
// so the axis/tooltip formatters can be exercised directly.
vi.mock('echarts-for-react', () => ({
  default: (props: { option: Record<string, unknown> }) => {
    mockOption.current = props.option
    return <div data-testid="echarts" />
  },
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

interface XAxisOption {
  axisLabel: { formatter: (value: string) => string }
}

interface TooltipOption {
  formatter: (params: unknown) => string
}

describe('TrendChart', () => {
  beforeEach(() => {
    mockOption.current = null
  })

  it('renders the chart when series has data', () => {
    render(<TrendChart data={validData} />)
    expect(screen.getByTestId('echarts')).toBeInTheDocument()
  })

  it('formats x-axis buckets as compact labels', () => {
    render(<TrendChart data={validData} />)
    const xAxis = mockOption.current?.xAxis as XAxisOption | undefined
    expect(xAxis?.axisLabel.formatter('2026-W23')).toBe('Jun 1')
  })

  it('formats tooltip buckets as full dates', () => {
    render(<TrendChart data={validData} />)
    const tooltip = mockOption.current?.tooltip as TooltipOption | undefined
    expect(tooltip?.formatter([{ axisValue: '2026-W23', value: 51 }])).toBe(
      '1 Jun 2026: 51 bpm',
    )
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
