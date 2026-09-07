import { describe, it, expect } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { App } from '../src/app'
import type { Settings } from '../src/api/settings'

const SETTINGS: Settings = {
  dataset: {
    id: 'ds_1',
    content_hash_prefix: 'abc',
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
  provider: { mode: 'local_only', model: null, egress_categories: [] },
  storage: {
    app_state_bytes: 8192,
    health_db_bytes: 4096,
    cache: { entries: 0, bytes: 0 },
    conversations: 0,
    saved_views: 0,
    diagnostics_events: 0,
  },
  quality: {
    active: true,
    parser_version: 'v2',
    schema_version: '1',
    coverage_start: '2026-01-01',
    coverage_end: '2026-08-31',
    warnings: [],
    metric_states: {},
    vocabulary: [],
  },
}

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/conversations', () => HttpResponse.json([])),
  http.get('/api/settings', () => HttpResponse.json(SETTINGS)),
)
beforeAll(() => server.listen())
afterEach(() => {
  server.resetHandlers()
  window.history.replaceState({}, '', window.location.pathname)
})
afterAll(() => server.close())

describe('App', () => {
  it('renders the heading', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument())
  })

  it('keeps the URL tab in sync when switching views', async () => {
    render(<App />)
    expect(screen.getByPlaceholderText('Search local conversations')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(window.location.search).toBe('?tab=settings')
    await screen.findByText('Settings & data controls')
  })

  it('shows a fallback while loading a code-split tab', async () => {
    server.use(
      http.get('/api/saved-views', () => HttpResponse.json([])),
      http.get('/api/dashboard/summary', () => HttpResponse.json({ days: [] })),
      http.get('/api/dashboard/workouts', () =>
        HttpResponse.json({ workouts: [], next_cursor: null }),
      ),
      http.get('/api/dashboard/steps', () =>
        HttpResponse.json({
          metric_label: 'Steps',
          metric_unit: 'count',
          granularity: 'day',
          series: [],
        }),
      ),
      http.get('/api/dashboard/heart', () =>
        HttpResponse.json({
          metric_label: 'Heart rate',
          metric_unit: 'bpm',
          granularity: 'week',
          series: [],
        }),
      ),
      http.get('/api/dashboard/sleep', () =>
        HttpResponse.json({
          metric_label: 'Sleep',
          metric_unit: 'hours',
          granularity: 'day',
          series: [],
        }),
      ),
      http.get('/api/dashboard/sleep/stages', () =>
        HttpResponse.json({
          total_asleep_hours: 0,
          stages_hours: {},
          stage_data_available: false,
          message: 'No stage data.',
        }),
      ),
      http.get('/api/dashboard/capabilities', () => HttpResponse.json({ capabilities: [] })),
      http.get('/api/status', () =>
        HttpResponse.json({ readiness: 'no_active_import', dataset: null }),
      ),
    )
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Dashboard' }))
    expect(await screen.findByTestId('tab-loading')).toBeInTheDocument()
    await screen.findByText('Activity Rings (Latest available day)')
  })

  it('restores the active tab from the URL on popstate (back/forward)', async () => {
    render(<App />)
    expect(screen.getByPlaceholderText('Search local conversations')).toBeInTheDocument()

    // Browser forward to the settings entry.
    act(() => {
      window.history.pushState({}, '', '?tab=settings')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await screen.findByText('Settings & data controls')

    // Back to chat (initial entry, no query string).
    act(() => {
      window.history.pushState({}, '', '?tab=chat')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.getByPlaceholderText('Search local conversations')).toBeInTheDocument()

    // Unknown tab resolves to the chat fallback, matching initialTab().
    act(() => {
      window.history.pushState({}, '', '?tab=unknown')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.getByPlaceholderText('Search local conversations')).toBeInTheDocument()
  })
})
