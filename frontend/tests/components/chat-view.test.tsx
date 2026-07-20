import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ChatView } from '@/components/chat-view'

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/conversations', () => HttpResponse.json([])),
  http.post('/api/conversations', () => HttpResponse.json({ id: 'cv_test' })),
)
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
  metadata: { api_version: 'v1' as const, provenance: 'deterministic_local' as const },
}

describe('ChatView', () => {
  it('renders idle state initially', async () => {
    render(<ChatView />)
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
    await act(async () => {})
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

  it('cancels an in-flight request while keeping a retryable visible turn', async () => {
    server.use(http.post('/api/chat', () => new Promise(() => {})))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByText('This request was cancelled.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('renders a workout card template on success with the query shown above', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    // Query is displayed above the answer
    expect(screen.getByText('last run')).toBeInTheDocument()
    expect(screen.getByText('Your last run was on June 5.')).toBeInTheDocument()
    expect(screen.getByText('Deterministic local answer')).toBeInTheDocument()
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

  it('restores a persisted failed turn as a visible retryable transcript item', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          { id: 'cv_failed', title: 'Retry me', created_at: 'now', updated_at: 'now' },
        ]),
      ),
      http.get('/api/conversations/cv_failed/turns', () =>
        HttpResponse.json([
          {
            question: 'Last run?',
            state: 'failed',
            response_json: null,
            error_message: 'The answer could not be completed.',
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Retry me' }))
    expect(await screen.findByText('The answer could not be completed.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('renames a selected local conversation without touching health data', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          {
            id: 'cv_test',
            title: 'Morning runs',
            created_at: '2026-06-05T00:00:00Z',
            updated_at: '2026-06-05T00:00:00Z',
          },
        ]),
      ),
      http.patch('/api/conversations/cv_test', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Weekend runs' })
        return HttpResponse.json({ ok: true })
      }),
    )
    const prompt = vi.spyOn(window, 'prompt').mockReturnValue('Weekend runs')
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Rename Morning runs' }))
    await waitFor(() => expect(prompt).toHaveBeenCalledWith('Rename this local conversation', 'Morning runs'))
    prompt.mockRestore()
  })

  it('seed prompt submits directly and shows the query', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(screen.getByRole('button', { name: /last long run/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    // Query label is visible
    expect(screen.getByText('Query')).toBeInTheDocument()
  })
})
