import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createSavedView, listSavedViews } from '@/api/saved-views'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('saved views API', () => {
  it('lists and creates local dashboard views', async () => {
    server.use(
      http.get('/api/saved-views', () =>
        HttpResponse.json([{ id: 'sv_1', title: 'June', query: { tab: 'overview' } }]),
      ),
      http.post('/api/saved-views', async ({ request }) => {
        expect(await request.json()).toEqual({
          title: 'June',
          query: { tab: 'overview', start: '2026-06-01', end: '2026-06-30' },
        })
        return HttpResponse.json({ id: 'sv_2' })
      }),
    )
    expect(await listSavedViews()).toHaveLength(1)
    await expect(
      createSavedView('June', { tab: 'overview', start: '2026-06-01', end: '2026-06-30' }),
    ).resolves.toBe('sv_2')
  })

  it('rejects failed saved-view requests', async () => {
    server.use(http.get('/api/saved-views', () => HttpResponse.json({}, { status: 500 })))
    await expect(listSavedViews()).rejects.toThrow('Saved view request failed: 500')
  })
})
