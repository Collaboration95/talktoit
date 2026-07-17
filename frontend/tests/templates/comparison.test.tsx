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
