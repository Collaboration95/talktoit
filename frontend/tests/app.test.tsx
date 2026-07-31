import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { App } from '../src/app'

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/conversations', () => HttpResponse.json([])),
)
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('App', () => {
  it('renders the heading', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument())
  })
})
