import { render, screen } from '@testing-library/react'
import { TemplateDispatch } from '@/components/template-dispatch'

const gate = vi.hoisted(() => ({
  loads: 0,
}))
vi.mock('@/charts/trend-line', () => {
  gate.loads += 1
  return { TrendLine: ({ title }: { title: string }) => <div>{title} canvas</div> }
})

it('defers chart code until a nonempty trend, preserving text, comparison facts and fallback', async () => {
  const view = render(
    <TemplateDispatch
      envelope={{
        template_id: 'comparison',
        narrative: '',
        data: {
          title: 'Steps comparison',
          this_period_label: 'June',
          last_period_label: 'May',
          metrics: [
            {
              label: 'Steps',
              unit: 'count',
              this_value: null,
              last_value: 4000,
              delta: null,
              direction: 'flat',
              direction_tone: 'neutral',
              this_observed_days: 0,
              this_requested_days: 7,
              last_observed_days: 3,
              last_requested_days: 7,
            },
          ],
        },
      }}
    />,
  )
  expect(gate.loads).toBe(0)
  expect(screen.getByText('0/7 days')).toBeInTheDocument()
  expect(screen.getByText('3/7 days')).toBeInTheDocument()
  view.rerender(
    <TemplateDispatch
      envelope={{
        template_id: 'trend_chart',
        narrative: 'Includes awake and in-bed records.',
        data: {
          title: 'Sleep interval coverage',
          metric_label: 'Sleep',
          metric_unit: 'hours',
          granularity: 'day',
          series: [],
        },
      }}
    />,
  )
  expect(screen.getByText(/Try a wider date range/)).toBeInTheDocument()
  expect(gate.loads).toBe(0)
  view.rerender(
    <>
      <p>Show my sleep last week</p>
      <TemplateDispatch
        envelope={{
          template_id: 'trend_chart',
          narrative: 'Includes awake and in-bed records.',
          data: {
            title: 'Sleep interval coverage',
            metric_label: 'Sleep',
            metric_unit: 'hours',
            granularity: 'day',
            series: [{ bucket: '2024-12-31', value: 2.5 }],
          },
        }}
      />
    </>,
  )
  expect(screen.getByText('Show my sleep last week')).toBeInTheDocument()
  expect(screen.getByText(/Includes awake and in-bed/)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Loading chart')
  expect(await screen.findByText('Sleep interval coverage canvas')).toBeInTheDocument()
  view.rerender(
    <TemplateDispatch envelope={{ template_id: 'future_type', narrative: '', data: {} }} />,
  )
  expect(screen.getByText(/Unknown template/)).toBeInTheDocument()
})
