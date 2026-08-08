import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { render, screen } from '@testing-library/react'
import { useBackendHealth } from '@/lib/use-backend-health'

const server = setupServer(http.get('/health', () => HttpResponse.json({ status: 'ok' })))

function Probe() {
  const backendDown = useBackendHealth()
  return <div>{backendDown ? 'DOWN' : 'UP'}</div>
}

describe('useBackendHealth', () => {
  it('reports the backend up when /health responds OK', async () => {
    render(<Probe />)
    expect(await screen.findByText('UP')).toBeInTheDocument()
  })

  it('reports the backend down on a 5xx response', async () => {
    server.use(http.get('/health', () => HttpResponse.json({}, { status: 503 })))
    render(<Probe />)
    expect(await screen.findByText('DOWN')).toBeInTheDocument()
  })

  it('reports the backend down when /health rejects', async () => {
    server.use(http.get('/health', () => HttpResponse.error()))
    render(<Probe />)
    expect(await screen.findByText('DOWN')).toBeInTheDocument()
  })
})

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
