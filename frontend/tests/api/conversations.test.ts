import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import {
  archiveConversation,
  createConversation,
  deleteConversation,
  getConversationTurns,
  listConversations,
  renameConversation,
} from '@/api/conversations'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('local conversation API', () => {
  it('creates, searches, reads, renames, archives, and deletes local history', async () => {
    server.use(
      http.post('/api/conversations', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Runs' })
        return HttpResponse.json({ id: 'cv_1' })
      }),
      http.get('/api/conversations', ({ request }) => {
        expect(new URL(request.url).searchParams.get('search')).toBe('morning run')
        return HttpResponse.json([
          { id: 'cv_1', title: 'Runs', created_at: 'now', updated_at: 'now' },
        ])
      }),
      http.get('/api/conversations/cv_1/turns', () =>
        HttpResponse.json([
          {
            id: 'tr_1',
            question: 'Last run?',
            state: 'completed',
            response_json: '{"template_id":"fallback"}',
          },
        ]),
      ),
      http.patch('/api/conversations/cv_1', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Morning runs' })
        return HttpResponse.json({ ok: true })
      }),
      http.post('/api/conversations/cv_1/archive', () => HttpResponse.json({ ok: true })),
      http.delete('/api/conversations/cv_1', () => HttpResponse.json({ ok: true })),
    )

    expect(await createConversation('Runs')).toBe('cv_1')
    expect(await listConversations('morning run')).toHaveLength(1)
    expect(await getConversationTurns('cv_1')).toEqual([
      {
        id: 'tr_1',
        question: 'Last run?',
        state: 'completed',
        response_json: '{"template_id":"fallback"}',
      },
    ])
    await renameConversation('cv_1', 'Morning runs')
    await archiveConversation('cv_1')
    await deleteConversation('cv_1')
  })

  it('rejects failed local-history requests', async () => {
    server.use(http.get('/api/conversations', () => HttpResponse.json({}, { status: 500 })))
    await expect(listConversations()).rejects.toThrow('Could not load conversations')
  })
})
