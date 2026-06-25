import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ChatView } from '@/components/chat-view'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Mock echarts-for-react and Tremor for jsdom
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))
vi.mock('@tremor/react', () => ({ BarList: () => <div data-testid="bar-list" /> }))

const WORKOUT_ENVELOPE = {
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
  narrative: 'Your last run was on June 5.',
}

describe('ChatView', () => {
  it('renders idle state initially', () => {
    render(<ChatView />)
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
  })

  it('shows loading state while request is in flight', async () => {
    let resolve: (v: Response) => void
    server.use(
      http.post('/api/chat', () => new Promise((r) => { resolve = r }).then(() =>
        HttpResponse.json(WORKOUT_ENVELOPE)
      )),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(screen.getByText(/thinking about/i)).toBeInTheDocument()
    resolve!(new Response())
  })

  it('renders a workout card template on success', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    expect(screen.getByText('Your last run was on June 5.')).toBeInTheDocument()
  })

  it('renders error state on API failure', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json({}, { status: 500 })))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'bad question')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => {
      expect(screen.getByText(/request failed/i)).toBeInTheDocument()
    })
  })

  it('seed prompt submits directly', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(screen.getByRole('button', { name: /last long run/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
  })
})
