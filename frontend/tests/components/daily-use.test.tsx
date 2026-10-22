import { act, render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { SettingsView } from '@/components/settings-view'
import { ChatView } from '@/components/chat-view'
import { App } from '@/app'
import { TemplateDispatch } from '@/components/template-dispatch'

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))
vi.mock('@tremor/react', () => ({ BarList: () => <div /> }))
const settings = {
  dataset: {
    counts: { records: 7, workouts: 0 },
    id: 'ds_test',
    warnings: [],
    coverage_start: '2026-01-01',
    coverage_end: '2026-01-31',
    imported_at: '2026-02-01T00:00:00Z',
    activated_at: '2026-02-01T00:00:00Z',
  },
  provider: { provider: 'local', mode: 'local_only', egress_categories: [] },
  storage: { cache: { entries: 0, bytes: 0 } },
  quality: {
    active: true,
    coverage_start: '2026-01-01',
    coverage_end: '2026-01-31',
    metric_states: { steps: 'available' },
    warnings: [],
  },
}
const job = {
  id: 'j1',
  filename: 'export.xml',
  state: 'running',
  progress: 10,
  report: null,
  error: null,
}
const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/settings', () => HttpResponse.json(settings)),
  http.get('/api/conversations', () => HttpResponse.json([])),
  http.get('/api/imports', () => HttpResponse.json([])),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  window.history.replaceState({}, '', '/')
})
afterAll(() => server.close())

it('offers steps-only prompts and retains the selected question with its answer', async () => {
  server.use(
    http.post('/api/conversations', () => HttpResponse.json({ id: 'c1' })),
    http.post('/api/chat', () =>
      HttpResponse.json({
        template_id: 'fallback',
        data: { text: 'No matching measurements.', table: null, reason: 'no_matching_data' },
        narrative: '',
      }),
    ),
  )
  render(<ChatView />)
  const prompt = await screen.findByRole('button', { name: 'Show my steps trend this year' })
  expect(screen.queryByRole('button', { name: /last.*run|compare|sleep/i })).not.toBeInTheDocument()
  await userEvent.click(prompt)
  expect(await screen.findByText('No matching measurements.')).toBeInTheDocument()
  expect(screen.getByText('Show my steps trend this year')).toBeInTheDocument()
  expect(screen.queryByText(/start it in Settings/i)).not.toBeInTheDocument()
})

it('offers workout prompts only for workouts and no invented prompts for unsupported metrics', async () => {
  server.use(
    http.get('/api/settings', () =>
      HttpResponse.json({
        ...settings,
        dataset: { ...settings.dataset, counts: { workouts: 3 } },
        quality: { ...settings.quality, metric_states: {} },
      }),
    ),
  )
  const view = render(<ChatView />)
  expect(await screen.findByRole('button', { name: 'Show my last workout' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /steps trend/i })).not.toBeInTheDocument()
  view.unmount()
  server.use(
    http.get('/api/settings', () =>
      HttpResponse.json({
        ...settings,
        quality: { ...settings.quality, metric_states: { sleep: 'available' } },
      }),
    ),
  )
  render(<ChatView />)
  expect(await screen.findByText(/No supported starter questions/i)).toBeInTheDocument()
})

it('guides a first import and refreshes capabilities on return', async () => {
  let imported = false
  server.use(
    http.get('/api/settings', () =>
      HttpResponse.json(imported ? settings : { ...settings, dataset: null }),
    ),
  )
  render(<App />)
  await userEvent.click(await screen.findByRole('button', { name: /open settings to import/i }))
  expect(await screen.findByText('Import Apple Health data')).toBeInTheDocument()
  expect(screen.getByText(/Export All Health Data/i)).toBeInTheDocument()
  expect(screen.getByText(/companion GPX files/i)).toBeInTheDocument()
  imported = true
  await userEvent.click(screen.getByRole('button', { name: 'Chat' }))
  expect(
    await screen.findByRole('button', { name: 'Show my steps trend this year' }),
  ).toBeInTheDocument()
})

it('recovers capability loading failures with retry', async () => {
  server.use(http.get('/api/settings', () => new HttpResponse(null, { status: 500 })))
  render(<ChatView />)
  await screen.findByText(/Could not load available questions/i)
  server.use(http.get('/api/settings', () => HttpResponse.json(settings)))
  await userEvent.click(screen.getByRole('button', { name: 'Retry available questions' }))
  expect(
    await screen.findByRole('button', { name: 'Show my steps trend this year' }),
  ).toBeInTheDocument()
})

it.each(['cancelled', 'succeeded', 'failed'])(
  'rediscovers a running import and handles %s cancellation outcome',
  async (outcome) => {
    let terminal = false
    let uploads = 0
    server.use(
      http.get('/api/imports', () => HttpResponse.json([job])),
      http.post('/api/imports', () => {
        uploads++
        return HttpResponse.json(job)
      }),
      http.get('/api/imports/j1', () =>
        HttpResponse.json(
          terminal
            ? {
                ...job,
                state: outcome === 'succeeded' ? 'succeeded' : 'failed',
                error:
                  outcome === 'cancelled'
                    ? 'The import was cancelled.'
                    : outcome === 'failed'
                      ? 'The import failed.'
                      : null,
                report: { counts: { workouts: 3 } },
              }
            : job,
        ),
      ),
      http.delete('/api/imports/j1', () => {
        terminal = true
        return new HttpResponse(null, { status: 409 })
      }),
    )
    const view = render(<SettingsView />)
    await screen.findByRole('button', { name: 'Cancel import' })
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    view.unmount()
    render(<SettingsView />)
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel import' }))
    await waitFor(() => expect(screen.getByLabelText('Apple Health export file')).toBeEnabled())
    if (outcome === 'cancelled')
      expect(screen.getByText('The import was cancelled.')).toBeInTheDocument()
    if (outcome === 'succeeded') {
      expect(screen.getByText(/3 workouts/)).toBeInTheDocument()
      expect(screen.queryByText(/Imported 0 records/)).not.toBeInTheDocument()
    }
    expect(uploads).toBe(0)
  },
)

it('reports a disappeared job honestly and restores controls', async () => {
  server.use(
    http.get('/api/imports', () => HttpResponse.json([job])),
    http.get('/api/imports/j1', () => new HttpResponse(null, { status: 404 })),
  )
  render(<SettingsView />)
  expect(
    await screen.findByText(/unknown or interrupted/i, {}, { timeout: 3000 }),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('Apple Health export file')).toBeEnabled()
})

it('aborts import polling on unmount', async () => {
  let aborted = false
  server.use(
    http.get('/api/imports', () => HttpResponse.json([job])),
    http.get('/api/imports/j1', async ({ request }) => {
      request.signal.addEventListener('abort', () => {
        aborted = true
      })
      await delay('infinite')
    }),
  )
  const view = render(<SettingsView />)
  await screen.findByRole('button', { name: 'Cancel import' })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 850))
  })
  view.unmount()
  await waitFor(() => expect(aborted).toBe(true))
})

it('renders reason-specific fallback headings without a model remedy for unsupported requests', () => {
  render(
    <TemplateDispatch
      envelope={{
        template_id: 'fallback',
        data: {
          question: 'q',
          text: 'Pace ranking is unsupported. Try Top 5 longest runs this year.',
          table: null,
          reason: 'unsupported',
        },
        narrative: '',
      }}
    />,
  )
  expect(screen.getByRole('heading', { name: 'Not supported yet' })).toBeInTheDocument()
  expect(screen.queryByText(/start.*model/i)).not.toBeInTheDocument()
})

it('keeps saved egress visible until provider changes are saved', async () => {
  const { within } = await import('@testing-library/react')
  let saved = settings
  server.use(
    http.get('/api/settings', () => HttpResponse.json(saved)),
    http.put('/api/settings/provider', async ({ request }) => {
      const body = (await request.json()) as { provider: string; mode: string }
      saved = {
        ...settings,
        provider: {
          ...settings.provider,
          ...body,
          egress_categories:
            body.mode === 'remote_planning'
              ? ['question text and dataset metadata (planning)']
              : [],
        },
      }
      return HttpResponse.json(saved.provider)
    }),
  )
  render(<SettingsView />)
  const privacy = await screen.findByRole('region', { name: 'Privacy' })
  expect(within(privacy).getByText('None — everything stays on this device')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Groq' }))
  await userEvent.selectOptions(screen.getByRole('combobox'), 'remote_planning')
  expect(within(privacy).getByText('None — everything stays on this device')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Save provider' }))
  expect(
    await screen.findByText('question text and dataset metadata (planning)'),
  ).toBeInTheDocument()
})

it('does not let a stale running poll replace the cancelled job or a newer upload', async () => {
  let finishPoll: (() => void) | undefined
  let pollStarted = false
  server.use(
    http.get('/api/imports', () => HttpResponse.json([job])),
    http.get('/api/imports/j1', async () => {
      pollStarted = true
      await new Promise<void>((resolve) => {
        finishPoll = resolve
      })
      return HttpResponse.json(job)
    }),
    http.delete('/api/imports/j1', () =>
      HttpResponse.json({ ...job, state: 'failed', error: 'The import was cancelled.' }),
    ),
    http.post('/api/imports', () =>
      HttpResponse.json({
        ...job,
        id: 'j2',
        state: 'succeeded',
        report: { counts: { workouts: 3 } },
      }),
    ),
  )
  render(<SettingsView />)
  await screen.findByRole('button', { name: 'Cancel import' })
  await waitFor(() => expect(pollStarted).toBe(true), { timeout: 2000 })
  await userEvent.click(screen.getByRole('button', { name: 'Cancel import' }))
  expect(await screen.findByText('The import was cancelled.')).toBeInTheDocument()
  const file = new File(['<HealthData />'], 'export.xml', { type: 'application/xml' })
  Object.defineProperty(file, 'arrayBuffer', {
    value: async () => new TextEncoder().encode('<HealthData />').buffer,
  })
  await userEvent.upload(screen.getByLabelText('Apple Health export file'), file)
  await userEvent.click(screen.getByRole('button', { name: 'Import export' }))
  expect(await screen.findByText('Imported 3 workouts.')).toBeInTheDocument()
  await act(async () => {
    finishPoll?.()
  })
  expect(screen.getByText('Imported 3 workouts.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Cancel import' })).not.toBeInTheDocument()
})

it('keeps polling and offers retry when cancellation fails and the job is still running', async () => {
  server.use(
    http.get('/api/imports', () => HttpResponse.json([job])),
    http.get('/api/imports/j1', () => HttpResponse.json(job)),
    http.delete('/api/imports/j1', () => new HttpResponse(null, { status: 500 })),
  )
  render(<SettingsView />)
  await userEvent.click(await screen.findByRole('button', { name: 'Cancel import' }))
  expect(await screen.findByText(/Cancellation was not confirmed/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Cancel import' })).toBeEnabled()
  expect(screen.getByLabelText('Apple Health export file')).toBeDisabled()
})
