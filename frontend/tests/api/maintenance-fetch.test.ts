import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { delay, http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { askQuestion } from '@/api/chat'

const server = setupServer()

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('supported test-toolchain fetch integration', () => {
  it('decodes a real MSW response with a jsdom AbortSignal', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json({
          template_id: 'fallback',
          data: { message: 'Try a workout question.' },
          narrative: 'Synthetic fixture.',
        }),
      ),
    )
    const controller = new AbortController()
    const result = await askQuestion('synthetic question', { signal: controller.signal })
    expect(result.template_id).toBe('fallback')
  })

  it('rejects a real intercepted fetch when the jsdom caller cancels', async () => {
    let started!: () => void
    const received = new Promise<void>((resolve) => {
      started = resolve
    })
    server.use(
      http.post('/api/chat', async () => {
        started()
        await delay(30)
        return HttpResponse.json({ template_id: 'fallback', data: { message: 'Synthetic' } })
      }),
    )
    const controller = new AbortController()
    const result = askQuestion('synthetic cancellation', { signal: controller.signal }).catch(
      (error: unknown) => error,
    )
    await received
    controller.abort()
    await expect(result).resolves.toMatchObject({ name: 'AbortError' })
  })
})
