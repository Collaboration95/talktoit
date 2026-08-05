import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DiagnosticsView } from '@/components/diagnostics-view'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const SUMMARY = {
  total_events: 4,
  by_category: {
    chat: { count: 2, mean_duration_ms: 20, p95_duration_ms: 25 },
    panel: { count: 2, mean_duration_ms: null, p95_duration_ms: null },
  },
  status_counts: { ok: 3, empty: 1 },
  cache: { hits: 1, misses: 1, hit_rate: 0.5 },
  cache_outcomes: { cached: 1, deterministic_local: 1 },
}

const EVENTS = {
  count: 2,
  events: [
    {
      id: 'de_1',
      category: 'chat',
      name: 'chat_request',
      status: 'ok',
      duration_ms: 20,
      counts: {},
      meta: { plan_mode: 'local' },
      created_at: '2026-08-05T00:00:00+00:00',
    },
    {
      id: 'de_2',
      category: 'panel',
      name: 'panel:steps',
      status: 'empty',
      duration_ms: null,
      counts: {},
      meta: { panel_name: 'steps' },
      created_at: '2026-08-05T00:00:01+00:00',
    },
  ],
}

function seedSuccess() {
  server.use(
    http.get('/api/diagnostics', () => HttpResponse.json(SUMMARY)),
    http.get('/api/diagnostics/events', () => HttpResponse.json(EVENTS)),
  )
}

describe('DiagnosticsView', () => {
  it('shows loading then the aggregate summary', async () => {
    seedSuccess()
    render(<DiagnosticsView />)
    expect(screen.getByText(/loading local diagnostics/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('4')).toBeInTheDocument())
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getAllByText(/chat requests/i).length).toBeGreaterThanOrEqual(1)
    await act(async () => {})
  })

  it('shows recent events and the empty-panel event', async () => {
    seedSuccess()
    render(<DiagnosticsView />)
    await waitFor(() => expect(screen.getByText('chat_request')).toBeInTheDocument())
    expect(screen.getByText('panel:steps')).toBeInTheDocument()
    await act(async () => {})
  })

  it('renders the empty state when no events exist', async () => {
    server.use(
      http.get('/api/diagnostics', () => HttpResponse.json({ ...SUMMARY, total_events: 0 })),
      http.get('/api/diagnostics/events', () => HttpResponse.json({ count: 0, events: [] })),
    )
    render(<DiagnosticsView />)
    await waitFor(() => expect(screen.getByText(/no events recorded yet/i)).toBeInTheDocument())
    await act(async () => {})
  })

  it('shows an error state when the API fails', async () => {
    server.use(
      http.get('/api/diagnostics', () => HttpResponse.json({}, { status: 500 })),
      http.get('/api/diagnostics/events', () => HttpResponse.json({}, { status: 500 })),
    )
    render(<DiagnosticsView />)
    await waitFor(() =>
      expect(screen.getByText(/diagnostics request failed: 500/i)).toBeInTheDocument(),
    )
    await act(async () => {})
  })

  it('clears diagnostics only after confirmation', async () => {
    seedSuccess()
    server.use(http.delete('/api/diagnostics', () => HttpResponse.json({ cleared: 4 })))
    render(<DiagnosticsView />)
    await waitFor(() => expect(screen.getByText(/clear diagnostics/i)).toBeInTheDocument())

    const clearButton = screen.getByRole('button', { name: /clear diagnostics/i })
    await userEvent.click(clearButton)
    expect(screen.getByRole('button', { name: /confirm: clear diagnostics\?/i })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /confirm: clear diagnostics\?/i }))
    await waitFor(() => expect(screen.getAllByText(/clear diagnostics/i).length).toBeGreaterThan(0))
    await act(async () => {})
  })
})
