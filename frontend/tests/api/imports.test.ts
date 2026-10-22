// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest'
import { cancelImport, fetchImport, listImports, startImport } from '@/api/imports'

afterEach(() => vi.restoreAllMocks())

it('uploads a native File with a Fetch-compatible body without requiring request-stream duplex', async () => {
  const file = new File(['<HealthData />'], 'synthetic export.xml', { type: 'application/xml' })
  const controller = new AbortController()
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
    // A naked ReadableStream body throws before sending in Chrome and native Fetch.
    expect(() => new Request('http://localhost/api/imports', init)).not.toThrow()
    return new Response(JSON.stringify({ id: 'j1', state: 'queued' }))
  })
  expect((await startImport(file, controller.signal)).id).toBe('j1')
  expect(fetchSpy.mock.calls[0]?.[0]).toBe('/api/imports?filename=synthetic%20export.xml')
  expect(fetchSpy.mock.calls[0]?.[1]?.signal).toBe(controller.signal)
})

it('lists, reads and cancels imports with the supplied abort signal and encoded identifiers', async () => {
  const controller = new AbortController()
  const fetchSpy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response('[]'))
    .mockResolvedValueOnce(new Response('{"id":"a/b","state":"running"}'))
    .mockResolvedValueOnce(new Response('{"id":"a/b","state":"failed"}'))
  expect(await listImports(controller.signal)).toEqual([])
  expect((await fetchImport('a/b', controller.signal)).state).toBe('running')
  expect((await cancelImport('a/b', controller.signal)).state).toBe('failed')
  expect(fetchSpy.mock.calls.map(([url]) => url)).toEqual([
    '/api/imports',
    '/api/imports/a%2Fb',
    '/api/imports/a%2Fb',
  ])
  expect(fetchSpy.mock.calls[2]?.[1]).toMatchObject({ method: 'DELETE', signal: controller.signal })
})
