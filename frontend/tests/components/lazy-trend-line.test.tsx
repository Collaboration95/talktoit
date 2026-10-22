import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LazyTrendLine } from '@/charts/lazy-trend-line'

vi.mock('@/charts/trend-line', () => {
  throw new Error('synthetic rejected chart module')
})

it('keeps formatted measured values, gaps and zero usable after a chart import failure', async () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    const user = userEvent.setup()
    render(
      <>
        <p>Show my measured sleep</p>
        <LazyTrendLine
          title="Sleep interval coverage"
          metricLabel="Sleep"
          metricUnit="hours"
          series={[
            { bucket: '2024-12-29', value: 2.5 },
            { bucket: '2024-12-30', value: null },
            { bucket: '2024-12-31', value: 0 },
          ]}
        />
      </>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Chart could not be loaded.')
    const table = screen.getByRole('table', { name: 'Sleep interval coverage' })
    expect(within(table).getByText('29 Dec 2024')).toBeInTheDocument()
    expect(within(table).getByText('150 min')).toBeInTheDocument()
    expect(within(table).getByText('—')).toBeInTheDocument()
    expect(within(table).getByText('0 min')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry chart' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Show my measured sleep')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
  } finally {
    errors.mockRestore()
  }
})
