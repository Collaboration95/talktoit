import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { App } from '@/app'
import * as dashboard from '@/api/dashboard'
import * as settings from '@/api/settings'
import * as conversations from '@/api/conversations'

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/saved-views', () => HttpResponse.json([])),
  http.get('/api/conversations', () => HttpResponse.json([])),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  vi.restoreAllMocks()
  server.resetHandlers()
  window.history.replaceState({}, '', '/')
})
afterAll(() => server.close())

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
const NO_DATA: settings.Settings = {
  dataset: null,
  provider: { mode: 'local_only', model: null, egress_categories: [] },
  storage: {
    app_state_bytes: 0,
    health_db_bytes: 0,
    cache: { entries: 0, bytes: 0 },
    conversations: 0,
    saved_views: 0,
    diagnostics_events: 0,
  },
  quality: {
    active: false,
    parser_version: null,
    schema_version: null,
    coverage_start: null,
    coverage_end: null,
    warnings: [],
    metric_states: {},
    vocabulary: [],
  },
}

it('commits enabled Chat with all eight panels pending, aborts old signals and ignores late completion', async () => {
  window.history.replaceState({}, '', '/?tab=dashboard')
  const pending: { signal: AbortSignal | undefined; release: () => void; fail: () => void }[] = []
  const later = <T,>(value: T, signal?: AbortSignal) =>
    new Promise<T>((resolve, reject) => {
      // Deliberately ignore abort: late responses must also be excluded by lifecycle guards.
      pending.push({
        signal,
        release: () => resolve(value),
        fail: () => reject(new Error('Synthetic late failure')),
      })
    })
  vi.spyOn(dashboard, 'fetchDatasetStatus').mockResolvedValue({
    readiness: 'ready',
    dataset: { coverage_start: '2024-01-01', coverage_end: '2024-06-28' },
  })
  vi.spyOn(dashboard, 'fetchSummary').mockImplementation((_scope, signal) => later([], signal))
  vi.spyOn(dashboard, 'fetchWorkouts').mockImplementation((_scope, _cursor, signal) =>
    later({ workouts: [], next_cursor: null }, signal),
  )
  vi.spyOn(dashboard, 'fetchTrend').mockImplementation((_endpoint, granularity, _scope, signal) =>
    later(
      { metric_label: 'Synthetic', metric_unit: 'count', granularity: granularity!, series: [] },
      signal,
    ),
  )
  vi.spyOn(dashboard, 'fetchSleepStages').mockImplementation((_scope, signal) =>
    later(
      {
        total_asleep_hours: 0,
        stages_hours: {},
        stage_data_available: false,
        message: 'Synthetic empty stage data',
      },
      signal,
    ),
  )
  vi.spyOn(dashboard, 'fetchCapabilities').mockImplementation((_scope, signal) => later([], signal))
  vi.spyOn(dashboard, 'fetchTrainingVolume').mockImplementation((_scope, granularity, signal) =>
    later(
      {
        granularity: granularity!,
        totals: { sessions: 0, duration_minutes: 0, distance_meters: 0, energy_kj: 0 },
        series: [],
        by_activity: [],
      },
      signal,
    ),
  )
  const capability = deferred<settings.Settings>()
  vi.spyOn(settings, 'fetchSettings').mockReturnValue(capability.promise)
  render(<App />)
  await waitFor(() => expect(pending).toHaveLength(8))
  expect(pending.every(({ signal }) => signal && !signal.aborted)).toBe(true)

  fireEvent.click(screen.getByRole('button', { name: 'Chat', exact: true }))
  const input = screen.getByPlaceholderText('Ask about your health data…')
  expect(input).toBeVisible()
  expect(input).toBeEnabled()
  expect(pending.every(({ signal }) => signal?.aborted)).toBe(true)
  expect(screen.getByText('Loading available questions…')).toBeInTheDocument()
  expect(screen.queryByTestId('panel-loading-volume')).not.toBeInTheDocument()
  await act(async () => {
    pending.forEach(({ release, fail }, index) => (index % 2 ? fail() : release()))
  })
  expect(input).toBeVisible()
  expect(screen.queryByRole('heading', { name: /Training Volume/ })).not.toBeInTheDocument()
  expect(screen.queryByText('Synthetic empty stage data')).not.toBeInTheDocument()
  await act(async () => capability.resolve(NO_DATA))
})

it('distinguishes shell readiness from pending Settings capabilities', async () => {
  const capability = deferred<settings.Settings>()
  vi.spyOn(settings, 'fetchSettings').mockReturnValue(capability.promise)
  render(<App />)
  expect(screen.getByPlaceholderText('Ask about your health data…')).toBeEnabled()
  expect(screen.getByText('Loading available questions…')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Open Settings to import' })).not.toBeInTheDocument()
  await act(async () => capability.resolve(NO_DATA))
  expect(screen.getByRole('button', { name: 'Open Settings to import' })).toBeVisible()
})

it('does not label a visible shell as a restored conversation before selected history arrives', async () => {
  vi.spyOn(settings, 'fetchSettings').mockResolvedValue(NO_DATA)
  vi.spyOn(conversations, 'listConversations').mockResolvedValue([
    {
      id: 'synthetic-history',
      title: 'Synthetic saved conversation',
      created_at: '2024-01-01',
      updated_at: '2024-01-01',
    },
  ])
  const history = deferred<conversations.StoredTurn[]>()
  vi.spyOn(conversations, 'getConversationTurns').mockReturnValue(history.promise)
  render(<App />)
  fireEvent.click(
    await screen.findByRole('button', { name: 'Synthetic saved conversation', exact: true }),
  )
  expect(screen.getByPlaceholderText('Ask about your health data…')).toBeEnabled()
  expect(screen.queryByText('Synthetic stored question')).not.toBeInTheDocument()
  expect(screen.queryByText('Synthetic stored answer')).not.toBeInTheDocument()
  await act(async () =>
    history.resolve([
      {
        id: 'synthetic-turn',
        question: 'Synthetic stored question',
        state: 'completed',
        response_json: JSON.stringify({
          template_id: 'workout_card',
          data: {
            activity_type: 'Running',
            date: '2024-01-01T08:00:00+08:00',
            duration_minutes: 30,
            avg_heart_rate: null,
            max_heart_rate: null,
            distance_meters: null,
            distance_unit: 'km',
            energy_burned_kj: null,
            elevation_ascent_meters: null,
          },
          narrative: 'Synthetic stored answer',
          metadata: {
            api_version: 'v1',
            provenance: 'deterministic_local',
            dataset_version_id: 'synthetic-history',
          },
        }),
        error_message: null,
      },
    ]),
  )
  expect(screen.getByText('Synthetic stored question')).toBeVisible()
  expect(screen.getByText('Synthetic stored answer')).toBeVisible()
})
