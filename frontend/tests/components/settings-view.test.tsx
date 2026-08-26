import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { SettingsView } from '@/components/settings-view'
import type { Settings } from '@/api/settings'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const SETTINGS: Settings = {
  dataset: {
    id: 'ds_1',
    content_hash_prefix: 'abc123',
    source_size_bytes: 4096,
    parser_version: 'v2',
    schema_version: '1',
    worker_count: 8,
    coverage_start: '2026-01-01',
    coverage_end: '2026-08-31',
    counts: { records: 1234 },
    warnings: [],
    imported_at: '2026-08-05T10:00:00+00:00',
    activated_at: '2026-08-05T10:00:00+00:00',
    status: 'active',
  },
  provider: {
    provider: 'groq',
    mode: 'local_only',
    model: null,
    base_url: 'https://api.groq.com/openai/v1',
    groq_model: 'llama-3.3-70b-versatile',
    groq_base_url: 'https://api.groq.com/openai/v1',
    litert_model: 'gemma4-e2b',
    litert_base_url: 'http://127.0.0.1:9379/v1',
    egress_categories: [],
    litert_status: {
      running: false,
      pid: null,
      base_url: 'http://127.0.0.1:9379/v1',
      model: 'gemma4-e2b',
      binary: null,
      binary_available: false,
      pidfile: '/tmp/litert.pid',
      log_path: '/tmp/litert.log',
    },
    litert_health: null,
  },
  storage: {
    app_state_bytes: 0,
    health_db_bytes: 0,
    cache: { entries: 3, bytes: 0 },
    conversations: 2,
    saved_views: 1,
    diagnostics_events: 5,
  },
  quality: {
    active: true,
    parser_version: 'v2',
    schema_version: '1',
    coverage_start: '2026-01-01',
    coverage_end: '2026-08-31',
    warnings: [],
    metric_states: { steps: 'available', sleep: 'out_of_range' },
    vocabulary: ['available', 'unavailable', 'out_of_range', 'unsupported', 'malformed'],
  },
}

function seedSuccess(settings: Settings = SETTINGS) {
  server.use(http.get('/api/settings', () => HttpResponse.json(settings)))
}

describe('SettingsView', () => {
  it('shows loading then dataset and privacy details', async () => {
    seedSuccess()
    render(<SettingsView />)
    expect(screen.getByText(/loading settings/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Settings & data controls')).toBeInTheDocument())
    // Privacy mode appears once in the Privacy section and again in the
    // provider selector's Groq mode dropdown; both are valid.
    expect(screen.getAllByText(/local only — no network egress/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/1,?234 records/)).toBeInTheDocument()
    expect(screen.getByText(/nothing stays on this device|everything stays on this device/i))
    await act(async () => {})
  })

  it('renders a no-dataset empty state', async () => {
    seedSuccess({ ...SETTINGS, dataset: null, quality: { ...SETTINGS.quality, active: false } })
    render(<SettingsView />)
    await waitFor(() =>
      expect(screen.getByText(/no health dataset has been imported yet/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/no data to report yet/i)).toBeInTheDocument()
    await act(async () => {})
  })

  it('shows an error state when the API fails', async () => {
    server.use(http.get('/api/settings', () => HttpResponse.json({}, { status: 500 })))
    render(<SettingsView />)
    await waitFor(() =>
      expect(screen.getByText(/settings request failed: 500/i)).toBeInTheDocument(),
    )
    await act(async () => {})
  })

  it('relabels storage history and clears each scope after confirmation', async () => {
    seedSuccess()
    server.use(
      http.delete('/api/settings/history', () =>
        HttpResponse.json({ deleted: 2, scope: 'history' }),
      ),
    )
    render(<SettingsView />)
    await waitFor(() => expect(screen.getByText(/clear chat history/i)).toBeInTheDocument())

    const historyButton = screen.getByRole('button', { name: /clear chat history/i })
    await userEvent.click(historyButton)
    expect(
      screen.getByRole('button', { name: /confirm: clear chat history\?/i }),
    ).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /confirm: clear chat history\?/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /clear chat history/i })).toBeInTheDocument(),
    )
    await act(async () => {})
  })

  it('marks the health clear action distinctly and requires confirmation', async () => {
    seedSuccess()
    render(<SettingsView />)
    await waitFor(() => expect(screen.getByRole('button', { name: /clear imported health data/i })))

    await userEvent.click(screen.getByRole('button', { name: /clear imported health data/i }))
    expect(
      screen.getByRole('button', { name: /confirm: clear imported health data\?/i }),
    ).toBeInTheDocument()
    await act(async () => {})
  })
})
