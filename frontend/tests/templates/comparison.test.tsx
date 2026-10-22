import { render, screen } from '@testing-library/react'
import { Comparison } from '@/templates/comparison'
import type { ComparisonData } from '@/types/templates'

const validData: ComparisonData = {
  title: 'Running: Jun vs May',
  this_period_label: 'Jun 2026',
  last_period_label: 'May 2026',
  metrics: [
    {
      label: 'Sessions',
      this_value: 14,
      last_value: 12,
      delta: 2,
      unit: 'sessions',
      direction: 'up',
    },
    {
      label: 'Distance',
      this_value: null,
      last_value: 100,
      delta: null,
      unit: 'km',
      direction: 'flat',
    },
  ],
}

describe('Comparison', () => {
  it('renders title', () => {
    render(<Comparison data={validData} />)
    expect(screen.getByText('Running: Jun vs May')).toBeInTheDocument()
  })

  it('renders period labels', () => {
    render(<Comparison data={validData} />)
    // Multiple elements with the period label (header + column header)
    expect(screen.getAllByText('Jun 2026').length).toBeGreaterThan(0)
  })

  it('renders em-dash for null values', () => {
    render(<Comparison data={validData} />)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('formats deltas with units', () => {
    render(<Comparison data={validData} />)
    expect(screen.getByText(/\+2 sessions/)).toBeInTheDocument()
  })
})

it('shows metric coverage, neutral signed deltas, zero and missing values', () => {
  render(
    <Comparison
      data={{
        ...validData,
        metrics: [
          {
            label: 'Steps per observed day',
            this_value: 8000,
            last_value: 5000,
            delta: 3000,
            unit: 'steps/day',
            direction: 'up',
            direction_tone: 'neutral',
            this_observed_days: 4,
            this_requested_days: 7,
            last_observed_days: 2,
            last_requested_days: 3,
            value_basis: 'observed_day_mean',
          },
          {
            label: 'HRV SDNN',
            this_value: 0,
            last_value: null,
            delta: null,
            unit: 'ms',
            direction: 'flat',
            direction_tone: 'neutral',
            this_observed_days: 1,
            this_requested_days: 7,
            last_observed_days: 0,
            last_requested_days: 3,
            value_basis: 'observation_mean',
          },
        ],
      }}
    />,
  )
  expect(screen.getByText('4/7 days')).toBeInTheDocument()
  expect(screen.getByText('2/3 days')).toBeInTheDocument()
  expect(screen.getByText('0/3 days')).toBeInTheDocument()
  expect(screen.getByText(/\+3,000 steps\/day/)).toHaveClass('text-gray-500')
  expect(screen.getByText('0 ms')).toBeInTheDocument()
  expect(screen.queryByText(/%/)).not.toBeInTheDocument()
})
