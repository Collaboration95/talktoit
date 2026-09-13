import { render, screen } from '@testing-library/react'
import { TemplateDispatch } from '@/components/template-dispatch'
import type { ChatEnvelope } from '@/types/templates'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))
vi.mock('@tremor/react', () => ({
  BarList: () => <div data-testid="bar-list" />,
}))

describe('TemplateDispatch', () => {
  it('dispatches workout_card correctly', () => {
    const envelope: ChatEnvelope = {
      template_id: 'workout_card',
      data: {
        activity_type: 'Running',
        date: '2026-06-05T07:00:00+08:00',
        duration_minutes: 45.5,
        avg_heart_rate: null,
        max_heart_rate: null,
        distance_meters: null,
        distance_unit: 'km',
        energy_burned_kj: null,
        elevation_ascent_meters: null,
      },
      narrative: 'Your last run.',
    }
    render(<TemplateDispatch envelope={envelope} />)
    expect(screen.getByText('Running')).toBeInTheDocument()
  })

  it('dispatches fallback for unknown template_id', () => {
    const envelope: ChatEnvelope = {
      template_id: 'unknown_template',
      data: {},
      narrative: '',
    }
    render(<TemplateDispatch envelope={envelope} />)
    expect(screen.getByText(/Unknown template/)).toBeInTheDocument()
  })

  it('dispatches ranked_list correctly', () => {
    const envelope: ChatEnvelope = {
      template_id: 'ranked_list',
      data: { title: 'Top Runs', rows: [] },
      narrative: '',
    }
    render(<TemplateDispatch envelope={envelope} />)
    expect(screen.getByText('Top Runs')).toBeInTheDocument()
  })

  it('degrades malformed template payloads to a safe fallback', () => {
    render(
      <TemplateDispatch
        envelope={{
          template_id: 'ranked_list',
          data: { title: 'Broken', rows: null },
          narrative: '',
        }}
      />,
    )
    expect(screen.getByText(/could not be displayed/i)).toBeInTheDocument()
  })

  it('keeps only well-formed rows from a malformed fallback table', () => {
    const envelope = {
      template_id: 'fallback',
      data: {
        question: 'q',
        table: [null, { key: 'Steps', value: '1000' }, { key: 'Missing value' }, 7],
        text: null,
      },
      narrative: '',
    } as unknown as ChatEnvelope

    render(<TemplateDispatch envelope={envelope} />)

    expect(screen.getByText('Steps')).toBeInTheDocument()
    expect(screen.getByText('1000')).toBeInTheDocument()
    expect(screen.queryByText('Missing value')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Here is what I found' })).toBeInTheDocument()
  })

  it('renders a safe fallback when every table row is malformed', () => {
    const envelope = {
      template_id: 'fallback',
      data: { question: 'q', table: [null, 3, 'row'], text: null },
      narrative: '',
    } as unknown as ChatEnvelope

    render(<TemplateDispatch envelope={envelope} />)

    expect(screen.getByRole('heading', { name: 'Answer unavailable' })).toBeInTheDocument()
  })
})
