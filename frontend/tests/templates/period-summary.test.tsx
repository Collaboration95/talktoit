import { render, screen } from '@testing-library/react'
import { PeriodSummary } from '@/templates/period-summary'
import type { PeriodSummaryData } from '@/types/templates'

const validData: PeriodSummaryData = {
  title: 'Last Week',
  period_start: '2026-06-01',
  period_end: '2026-06-07',
  metrics: [
    { label: 'Workouts', value: 5, unit: 'sessions' },
    { label: 'Total Distance', value: null, unit: 'km' },
  ],
}

describe('PeriodSummary', () => {
  it('renders title', () => {
    render(<PeriodSummary data={validData} />)
    expect(screen.getByText('Last Week')).toBeInTheDocument()
  })

  it('renders metric values', () => {
    render(<PeriodSummary data={validData} />)
    expect(screen.getByText('5 sessions')).toBeInTheDocument()
  })

  it('renders em-dash for null metric values', () => {
    render(<PeriodSummary data={validData} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
