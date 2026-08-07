import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import {
  clearDiagnostics,
  exportDiagnostics,
  fetchDiagnosticsEvents,
  fetchDiagnosticsSummary,
} from '@/api/diagnostics'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const SUMMARY = {
  total_events: 3,
  by_category: {
    chat: { count: 1, mean_duration_ms: 12.5, p95_duration_ms: 12.5 },
    panel: { count: 2, mean_duration_ms: null, p95_duration_ms: null },
  },
  status_counts: { ok: 3 },
  cache: { hits: 1, misses: 0, hit_rate: 1 },
  cache_outcomes: { cached: 1 },
}

describe('diagnostics API', () => {
  it('fetches the privacy-safe summary', async () => {
    server.use(http.get('/api/diagnostics', () => HttpResponse.json(SUMMARY)))
    await expect(fetchDiagnosticsSummary()).resolves.toEqual(SUMMARY)
  })

  it('fetches recent events with a category filter', async () => {
    server.use(
      http.get('/api/diagnostics/events', ({ request }) => {
        expect(new URL(request.url).searchParams.get('category')).toBe('chat')
        expect(new URL(request.url).searchParams.get('limit')).toBe('20')
        return HttpResponse.json({ count: 1, events: [] })
      }),
    )
    await expect(fetchDiagnosticsEvents('chat', 20)).resolves.toEqual({ count: 1, events: [] })
  })

  it('clears diagnostics and returns the deleted count', async () => {
    server.use(
      http.delete('/api/diagnostics', () => HttpResponse.json({ cleared: 3 })),
    )
    await expect(clearDiagnostics()).resolves.toBe(3)
  })

  it('exports a redacted payload only with confirmation', async () => {
    server.use(
      http.post('/api/diagnostics/export', async ({ request }) => {
        expect(await request.json()).toEqual({ confirmed: true })
        return HttpResponse.json({ redacted: true, export: SUMMARY })
      }),
    )
    await expect(exportDiagnostics()).resolves.toEqual({ redacted: true, export: SUMMARY })
  })

  it('rejects failed diagnostics requests', async () => {
    server.use(http.get('/api/diagnostics', () => HttpResponse.json({}, { status: 500 })))
    await expect(fetchDiagnosticsSummary()).rejects.toThrow('Diagnostics request failed: 500')
  })
})
