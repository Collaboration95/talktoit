import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { clearScope, fetchSettings } from '@/api/settings'
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
    mode: 'local_only',
    model: null,
    egress_categories: [],
  },
  storage: {
    app_state_bytes: 8192,
    health_db_bytes: 4096,
    cache: { entries: 3, bytes: 512 },
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

describe('settings API', () => {
  it('fetches the settings summary', async () => {
    server.use(http.get('/api/settings', () => HttpResponse.json(SETTINGS)))
    await expect(fetchSettings()).resolves.toEqual(SETTINGS)
  })

  it('sends an explicit scoped confirmation to clear a scope', async () => {
    server.use(
      http.delete('/api/settings/cache', async ({ request }) => {
        expect(await request.json()).toEqual({ confirm: true, scope: 'cache' })
        return HttpResponse.json({ cleared: 3, scope: 'cache' })
      }),
    )
    await expect(clearScope('cache')).resolves.toEqual({ cleared: 3, scope: 'cache' })
  })

  it('rejects failed settings requests', async () => {
    server.use(http.get('/api/settings', () => HttpResponse.json({}, { status: 500 })))
    await expect(fetchSettings()).rejects.toThrow('Settings request failed: 500')
  })
})
