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

  it('renders the chart when series has data', async () => {
    render(<TrendChart data={validData} />)
    expect(await screen.findByTestId('echarts')).toBeInTheDocument()
  })

  it('formats x-axis buckets as compact labels', async () => {
    render(<TrendChart data={validData} />)
    await screen.findByTestId('echarts')
    const xAxis = mockOption.current?.xAxis as XAxisOption | undefined
    expect(xAxis?.axisLabel.formatter('2026-W23')).toBe('Jun 1')
  })

  it('formats tooltip buckets as full dates', async () => {
    render(<TrendChart data={validData} />)
    await screen.findByTestId('echarts')
    const tooltip = mockOption.current?.tooltip as TooltipOption | undefined
    expect(tooltip?.formatter([{ axisValue: '2026-W23', value: 51 }])).toBe('1 Jun 2026: 51 bpm')
  })

  it('renders empty state when series is empty', () => {
    render(<TrendChart data={{ ...validData, series: [] }} />)
    expect(screen.getByText('No trend data available. Try a wider date range.')).toBeInTheDocument()
  })

  it('renders narrative when provided', async () => {
    render(<TrendChart data={validData} narrative="Steady HR this month." />)
    await screen.findByTestId('echarts')
    expect(screen.getByText('Steady HR this month.')).toBeInTheDocument()
  })
})

it('shows actionable empty state for all-null sleep without converting it to zero', () => {
  render(
    <TrendChart
      data={{
        title: 'Sleep interval coverage',
        metric_label: 'Sleep',
        metric_unit: 'hours',
        granularity: 'day',
        series: [{ bucket: '2026-06-01', value: null }],
      }}
      narrative="Includes awake and in-bed records."
    />,
  )
  expect(screen.getByText(/Try a wider date range/)).toBeInTheDocument()
  expect(screen.getByText(/Includes awake and in-bed/)).toBeInTheDocument()
})

it('keeps sleep hours on the axis and rounds tooltip durations to minutes', async () => {
  render(
    <TrendChart
      data={{
        title: 'Sleep interval coverage',
        metric_label: 'Sleep',
        metric_unit: 'hours',
        granularity: 'day',
        series: [{ bucket: '2026-06-01', value: 2.5 }],
      }}
    />,
  )
  await screen.findByTestId('echarts')
  const tooltip = mockOption.current?.['tooltip'] as TooltipOption
  expect(tooltip.formatter([{ axisValue: '2026-06-01', value: 2.5 }])).toBe('1 Jun 2026: 150 min')
  const axis = mockOption.current?.['yAxis'] as {
    axisLabel: { formatter: (value: number) => string }
  }
  expect(axis.axisLabel.formatter(2.5)).toBe('2.5')
})
