import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { askQuestion, ChatApiError } from '@/api/chat'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('askQuestion', () => {
  it('returns a chat envelope on success', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json({
          template_id: 'workout_card',
          data: { activity_type: 'Running' },
          narrative: 'Test.',
        }),
      ),
    )
    const result = await askQuestion('show my last run')
    expect(result.template_id).toBe('workout_card')
    expect(result.narrative).toBe('Test.')
  })

  it('throws ChatApiError on non-200 response', async () => {
    server.use(
      http.post('/api/chat', () => HttpResponse.json({ detail: 'error' }, { status: 500 })),
    )
    await expect(askQuestion('test')).rejects.toBeInstanceOf(ChatApiError)
  })
})
