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
      http.post('/api/chat', () =>
        HttpResponse.json(
          {
            detail: {
              api_version: 'v1',
              code: 'data_unavailable',
              message: 'Local health data is unavailable.',
              request_id: 'req-test',
            },
          },
          { status: 503 },
        ),
      ),
    )
    const failure = await askQuestion('test').catch((error: unknown) => error)
    expect(failure).toBeInstanceOf(ChatApiError)
    expect(failure).toMatchObject({
      status: 503,
      message: 'Local health data is unavailable.',
      code: 'data_unavailable',
      requestId: 'req-test',
    })
  })
})
