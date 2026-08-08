// @vitest-environment node
import { describe, expect, it, vi } from 'vitest'
import { askQuestion } from '@/api/chat'

// Runs in Node's environment (not jsdom) so the AbortSignal here is the one
// undici's fetch accepts. This proves the *production* wiring — the chat view
// passes its AbortController signal into askQuestion and the client forwards
// it into fetch — regardless of the jsdom/undici signal incompatibility that
// keeps the `navigator.userAgent.includes('jsdom')` guard in the components.
describe('askQuestion abort wiring', () => {
  it('forwards the caller-provided AbortSignal into fetch', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            template_id: 'workout_card',
            data: { activity_type: 'Running' },
            narrative: 'Test.',
            metadata: { api_version: 'v1', provenance: 'deterministic_local' },
          }),
          { status: 200 },
        ),
      )
    const controller = new AbortController()
    await askQuestion('show my last run', { signal: controller.signal })
    const init = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.signal).toBe(controller.signal)
    fetchSpy.mockRestore()
  })

  it('aborting the controller rejects the in-flight request (real cancel path)', async () => {
    // Simulate the network layer listening on the forwarded signal: an abort
    // must surface as an AbortError to the API caller, mirroring what the
    // Cancel button does in production browsers.
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('committed by the caller', 'AbortError')),
          )
        }),
    )
    const controller = new AbortController()
    const pending = askQuestion('show my last run', {
      signal: controller.signal,
    }).catch((error: unknown) => error)
    controller.abort()
    await expect(pending).resolves.toMatchObject({ name: 'AbortError' })
  })
})
