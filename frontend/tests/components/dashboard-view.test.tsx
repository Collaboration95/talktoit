import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DashboardView } from '@/components/dashboard-view'
import type { TrendResponse } from '@/api/dashboard'

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/conversations', () => HttpResponse.json([])),
  http.get('/api/saved-views', () => HttpResponse.json([])),
  http.get('/api/status', () =>
    HttpResponse.json({
      readiness: 'ready',
      dataset: { coverage_start: '2024-01-01', coverage_end: '2024-12-31' },
    }),
  ),
  http.get('/api/dashboard/sleep/stages', () =>
    HttpResponse.json({
      total_asleep_hours: 7.5,
      stages_hours: { Core: 3.5, REM: 2 },
      stage_data_available: true,
      message: 'Stages are measured from the selected sleep source.',
    }),
  ),
  http.get('/api/dashboard/workouts/1', () =>
    HttpResponse.json({
      id: 1,
      fingerprint: '0123456789abcdef',
      activity_type: 'Running',
      date: '2026-06-05T07:00:00+08:00',
      duration_minutes: 45.5,
      avg_heart_rate: 148,
      max_heart_rate: 171,
      distance_meters: 8500,
      distance_unit: 'm',
      energy_burned_kj: 2500,
      elevation_ascent_meters: 45.2,
      source_name: 'Apple Watch',
      gps_route: null,
      metadata: [],
      route: { state: 'missing', message: 'No route is available for this workout.' },
    }),
  ),
)
beforeAll(() => server.listen())
afterEach(() => {
  server.resetHandlers()
  window.history.replaceState({}, '', '/')
})
afterAll(() => server.close())

// Mock ECharts in jsdom — it can't render canvas
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))

const EMPTY_TREND: TrendResponse = {
  metric_label: 'Steps',
  metric_unit: 'count',
  granularity: 'day',
  series: [],
}

const STEPS_TREND: TrendResponse = {
  metric_label: 'Steps',
  metric_unit: 'count',
  granularity: 'day',
  series: [
    { bucket: '2026-06-05', value: 12100 },
    { bucket: '2026-06-06', value: 7600 },
  ],
}

const HEART_TREND: TrendResponse = {
  metric_label: 'Resting HR',
  metric_unit: 'bpm',
  granularity: 'week',
  series: [{ bucket: '2026-W23', value: 51 }],
}

const SLEEP_TREND: TrendResponse = {
  metric_label: 'Sleep',
  metric_unit: 'hours',
  granularity: 'day',
  series: [{ bucket: '2026-06-05', value: 7.5 }],
}

function setupHandlers() {
  server.use(
    http.get('/api/dashboard/summary', () =>
      HttpResponse.json({
        days: [
          {
            date: '2026-06-05',
            energy_kj: 3200,
            energy_goal_kj: 2500,
            exercise_min: 55,
            exercise_goal_min: 30,
            stand_hours: 14,
            stand_goal_hours: 12,
          },
        ],
      }),
    ),
    http.get('/api/dashboard/workouts', () =>
      HttpResponse.json({
        workouts: [
          {
            id: 1,
            activity_type: 'Running',
            date: '2026-06-05T07:00:00+08:00',
            duration_minutes: 45.5,
            avg_heart_rate: 148,
            distance_meters: 8500,
            energy_burned_kj: 2500,
            source_name: 'Apple Watch',
            fingerprint: '0123456789abcdef',
          },
        ],
      }),
    ),
    http.get('/api/dashboard/volume', () =>
      HttpResponse.json({
        granularity: 'week',
        totals: {
          bucket: 'total',
          sessions: 1,
          duration_minutes: 45.5,
          distance_meters: 8500,
          energy_kj: 2500,
        },
        series: [
          {
            bucket: '2026-W23',
            sessions: 1,
            duration_minutes: 45.5,
            distance_meters: 8500,
            energy_kj: 2500,
          },
        ],
        by_activity: [
          {
            activity_type: 'Running',
            sessions: 1,
            duration_minutes: 45.5,
            distance_meters: 8500,
            energy_kj: 2500,
          },
        ],
      }),
    ),
    http.get('/api/dashboard/steps', () => HttpResponse.json(STEPS_TREND)),
    http.get('/api/dashboard/heart', () => HttpResponse.json(HEART_TREND)),
    http.get('/api/dashboard/sleep/stages', () =>
      HttpResponse.json({
        total_asleep_hours: 7.5,
        stages_hours: { Core: 3.5, REM: 2 },
        stage_data_available: true,
        message: 'Stages are measured from the selected sleep source.',
      }),
    ),
    http.get('/api/dashboard/sleep', () => HttpResponse.json(SLEEP_TREND)),
    http.get('/api/dashboard/capabilities', () =>
      HttpResponse.json({
        capabilities: [
          { name: 'resting_hr', present: true, state: 'available' },
          { name: 'steps', present: true, state: 'available' },
          { name: 'sleep', present: true, state: 'available' },
          { name: 'hrv', present: true, state: 'available' },
          { name: 'workouts', present: true, state: 'available' },
        ],
      }),
    ),
    http.get('/api/saved-views', () => HttpResponse.json([])),
    http.get('/api/status', () =>
      HttpResponse.json({
        readiness: 'ready',
        dataset: { coverage_start: '2024-01-01', coverage_end: '2024-12-31' },
      }),
    ),
  )
}

describe('DashboardView', () => {
  it('anchors visible presets to imported coverage and scopes every panel consistently', async () => {
    setupHandlers()
    const requests: URL[] = []
    server.events.on('request:start', ({ request }) => {
      if (new URL(request.url).pathname.startsWith('/api/dashboard/'))
        requests.push(new URL(request.url))
    })
    const user = userEvent.setup()
    render(<DashboardView />)
    const preset = await screen.findByRole('button', { name: 'Latest 7 data days' })
    await waitFor(() => expect(preset).toBeEnabled())
    requests.length = 0
    await user.click(preset)
    await waitFor(() => expect(requests.length).toBe(8))
    for (const request of requests) {
      expect(request.searchParams.get('start')).toBe('2024-12-25')
      expect(request.searchParams.get('end')).toBe('2024-12-31')
    }
    expect(screen.getByLabelText('Active dashboard scope')).toHaveTextContent(
      '25 Dec 2024 to 31 Dec 2024',
    )
    expect(
      screen.getByRole('heading', { name: 'Training Volume (25 Dec 2024 to 31 Dec 2024)' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Latest 30 data days' }))
    expect(window.location.search).toContain('start=2024-12-02')
    await user.click(screen.getByRole('button', { name: 'All available data' }))
    expect(window.location.search).toContain('start=2024-01-01')
    expect(window.location.search).toContain('end=2024-12-31')
    server.events.removeAllListeners('request:start')
  })

  it('validates custom periods without requesting drafts and restores URL scope on navigation', async () => {
    setupHandlers()
    let requests = 0
    server.use(
      http.get('/api/dashboard/workouts', () => {
        requests++
        return HttpResponse.json({ workouts: [], next_cursor: null })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    const start = await screen.findByLabelText('Period start')
    const end = screen.getByLabelText('Period end')
    await waitFor(() => expect(start).toBeEnabled())
    await waitFor(() => expect(requests).toBe(1))
    fireEvent.change(start, { target: { value: '2024-02-30' } })
    fireEvent.change(end, { target: { value: '2024-03-31' } })
    await user.click(screen.getByRole('button', { name: 'Apply custom period' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/valid calendar dates/i)
    expect(requests).toBe(1)
    fireEvent.change(start, { target: { value: '2024-04-01' } })
    await user.click(screen.getByRole('button', { name: 'Apply custom period' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/start.*end/i)
    expect(requests).toBe(1)
    fireEvent.change(start, { target: { value: '2024-02-01' } })
    fireEvent.change(end, { target: { value: '2024-02-29' } })
    await user.click(screen.getByRole('button', { name: 'Apply custom period' }))
    await waitFor(() => expect(requests).toBe(2))
    const february = window.location.search
    await user.click(screen.getByRole('button', { name: 'Latest 7 data days' }))
    await act(async () => {
      window.history.replaceState({}, '', february)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(start).toHaveValue('2024-02-01')
    expect(end).toHaveValue('2024-02-29')
    expect(screen.getByLabelText('Active dashboard scope')).toHaveTextContent(
      '1 Feb 2024 to 29 Feb 2024',
    )
  })

  it('disables coverage presets when import coverage is missing or unavailable', async () => {
    setupHandlers()
    server.use(
      http.get('/api/status', () =>
        HttpResponse.json({ readiness: 'no_active_import', dataset: null }),
      ),
    )
    render(<DashboardView />)
    await waitFor(() =>
      expect(screen.getByText(/import data to choose a period/i)).toBeInTheDocument(),
    )
    expect(screen.getByRole('button', { name: 'Latest 7 data days' })).toBeDisabled()
    expect(screen.queryByLabelText('Imported data coverage')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save view' })).not.toBeInTheDocument()
  })

  it('saves the ordinary default dashboard and restores its default scope', async () => {
    setupHandlers()
    let saved: { title: string; query: Record<string, string> } | undefined
    server.use(
      http.post('/api/saved-views', async ({ request }) => {
        saved = (await request.json()) as typeof saved
        return HttpResponse.json({ id: 'sv_default' })
      }),
      http.get('/api/saved-views', () =>
        HttpResponse.json(saved ? [{ id: 'sv_default', ...saved }] : []),
      ),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.type(await screen.findByLabelText('Saved view name'), 'My default dashboard')
    await user.click(screen.getByRole('button', { name: 'Save view' }))
    await screen.findByRole('button', { name: 'My default dashboard' })
    expect(saved?.query).toEqual({ tab: 'workouts' })
    await user.click(screen.getByRole('button', { name: 'Latest 7 data days' }))
    await user.click(screen.getByRole('button', { name: 'My default dashboard' }))
    expect(window.location.search).not.toContain('start=')
    expect(window.location.search).toContain('tab=workouts')
    expect(screen.getByLabelText('Active dashboard scope')).toHaveTextContent(
      /default panel periods/i,
    )
  })

  it('round-trips an explicit saved period through application and URL navigation', async () => {
    setupHandlers()
    server.use(
      http.get('/api/saved-views', () =>
        HttpResponse.json([
          {
            id: 'sv_leap',
            title: 'Leap February',
            query: {
              tab: 'overview',
              start: '2024-02-01',
              end: '2024-02-29',
              source: 'Apple Watch',
            },
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: 'Leap February' }))
    expect(window.location.search).toContain('tab=workouts')
    const savedUrl = window.location.search
    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await act(async () => {
      window.history.replaceState({}, '', savedUrl)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.getByLabelText('Period start')).toHaveValue('2024-02-01')
    expect(screen.getByLabelText('Filter workouts by source')).toHaveValue('Apple Watch')
    expect(
      screen.getByRole('heading', { name: 'Daily Steps (1 Feb 2024 to 29 Feb 2024)' }),
    ).toBeInTheDocument()
  })

  it('does not invent imported coverage when the status request fails', async () => {
    setupHandlers()
    server.use(http.get('/api/status', () => HttpResponse.json({}, { status: 500 })))
    render(<DashboardView />)
    expect(await screen.findByText(/Could not load: import status/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Latest 7 data days' })).toBeDisabled()
    expect(screen.queryByLabelText('Imported data coverage')).not.toBeInTheDocument()
  })

  it('clears a coverage error after a successful retry', async () => {
    setupHandlers()
    let failing = true
    server.use(
      http.get('/api/status', () =>
        failing
          ? HttpResponse.json({}, { status: 500 })
          : HttpResponse.json({
              readiness: 'ready',
              dataset: { coverage_start: '2024-01-01', coverage_end: '2024-12-31' },
            }),
      ),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await screen.findByText(/Could not load: import status/)
    failing = false
    await user.click(screen.getByRole('button', { name: 'Retry unavailable panels' }))
    await screen.findByLabelText('Imported data coverage')
    expect(screen.queryByText(/Could not load: import status/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Latest 7 data days' })).toBeEnabled()
  })

  it('retains controls and selected filters across zero results, loading, failure and Reset', async () => {
    setupHandlers()
    let fail = false
    let release: (() => void) | undefined
    let block = false
    const all = [
      {
        id: 1,
        activity_type: 'Running',
        source_name: 'Apple Watch',
        date: '2024-12-30T07:00:00+08:00',
        duration_minutes: 30,
        avg_heart_rate: 140,
        distance_meters: 5000,
        energy_burned_kj: 1500,
        fingerprint: '0123456789abcdef',
      },
      {
        id: 2,
        activity_type: 'Cycling',
        source_name: 'Strava',
        date: '2024-12-29T07:00:00+08:00',
        duration_minutes: 60,
        avg_heart_rate: 130,
        distance_meters: 20000,
        energy_burned_kj: 2000,
        fingerprint: 'ffffffffffffffff',
      },
    ]
    server.use(
      http.get('/api/dashboard/workouts', async ({ request }) => {
        if (block)
          await new Promise<void>((resolve) => {
            release = resolve
          })
        if (fail) return HttpResponse.json({}, { status: 500 })
        const params = new URL(request.url).searchParams
        const workouts = all.filter(
          (row) =>
            (!params.get('source') || row.source_name === params.get('source')) &&
            (!params.get('activity_type') || row.activity_type === params.get('activity_type')) &&
            (!params.get('end') || row.date.slice(0, 10) <= params.get('end')!),
        )
        return HttpResponse.json({ workouts, next_cursor: null })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: /Running 1/ }))
    const source = screen.getByLabelText('Filter workouts by source')
    await user.selectOptions(source, 'Strava')
    expect(await screen.findByText(/no workouts match/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Running 0/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: /Cycling 0/ })).toBeInTheDocument()
    expect(source).toHaveValue('Strava')
    expect(screen.getByText(/counts.*loaded rows/i)).toBeInTheDocument()
    block = true
    await user.click(screen.getByRole('button', { name: 'Latest 7 data days' }))
    expect(await screen.findByTestId('panel-loading-workouts')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeEnabled()
    expect(source).toBeEnabled()
    await waitFor(() => expect(release).toBeDefined())
    fail = true
    await act(async () => release?.())
    expect(await screen.findByText(/could not load workouts/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset' })).toBeEnabled()
    block = false
    fail = false
    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await screen.findByRole('button', { name: /All 2/ })
    for (const key of ['start', 'end', 'source', 'activity_type'])
      expect(new URLSearchParams(window.location.search).has(key)).toBe(false)
  })

  it('ignores a pending pagination response after Reset changes the generation', async () => {
    setupHandlers()
    let release: (() => void) | undefined
    server.use(
      http.get('/api/dashboard/workouts', ({ request }) => {
        if (new URL(request.url).searchParams.has('cursor'))
          return new Promise((resolve) => {
            release = () =>
              resolve(
                HttpResponse.json({
                  workouts: [{ id: 99, activity_type: 'Stale row' }],
                  next_cursor: null,
                }),
              )
          })
        return HttpResponse.json({ workouts: [], next_cursor: 'next' })
      }),
    )
    const user = userEvent.setup()
    window.history.replaceState({}, '', '?tab=workouts&source=Strava')
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: 'Load more workouts' }))
    await waitFor(() => expect(release).toBeDefined())
    await user.click(screen.getByRole('button', { name: 'Reset' }))
    await act(async () => release?.())
    expect(screen.queryByText('Stale row')).not.toBeInTheDocument()
  })

  it('shows loading state initially', async () => {
    // Block requests so loading persists
    server.use(
      http.get('/api/dashboard/summary', () => new Promise(() => {})),
      http.get('/api/dashboard/workouts', () => new Promise(() => {})),
      http.get('/api/dashboard/volume', () => new Promise(() => {})),
      http.get('/api/dashboard/steps', () => new Promise(() => {})),
      http.get('/api/dashboard/heart', () => new Promise(() => {})),
      http.get('/api/dashboard/sleep', () => new Promise(() => {})),
      http.get('/api/dashboard/capabilities', () => new Promise(() => {})),
    )
    render(<DashboardView />)
    expect(screen.getByTestId('panel-loading-summary')).toBeInTheDocument()
    expect(screen.getByTestId('panel-loading-workouts')).toBeInTheDocument()
    expect(screen.getByText(/loading activity rings/i)).toBeInTheDocument()
    await act(async () => {})
  })

  it('renders a panel as soon as its own request resolves', async () => {
    setupHandlers()
    server.use(http.get('/api/dashboard/summary', () => new Promise(() => {})))
    render(<DashboardView />)

    expect(screen.getByTestId('panel-loading-summary')).toBeInTheDocument()
    expect(await screen.findByText('46 min')).toBeInTheDocument()
    expect(screen.getByTestId('panel-loading-summary')).toBeInTheDocument()
  })

  it('renders workout list after load', async () => {
    setupHandlers()
    render(<DashboardView />)
    await waitFor(() => {
      expect(screen.getAllByText('Running').length).toBeGreaterThanOrEqual(1)
    })
    // Check workout row details
    expect(screen.getByText('46 min')).toBeInTheDocument()
  })

  it('renders training volume totals and activity breakdown', async () => {
    setupHandlers()
    render(<DashboardView />)
    expect(
      await screen.findByText('Training Volume (3 Oct 2024 to 31 Dec 2024)'),
    ).toBeInTheDocument()
    expect((await screen.findAllByText('0.8 h')).length).toBeGreaterThan(0)
    expect(screen.getByText('Training volume by activity')).toBeInTheDocument()
  })

  it('switches training volume between weekly and monthly buckets', async () => {
    setupHandlers()
    let requestedGranularity = 'week'
    server.use(
      http.get('/api/dashboard/volume', ({ request }) => {
        requestedGranularity = new URL(request.url).searchParams.get('granularity') ?? ''
        return HttpResponse.json({
          granularity: requestedGranularity,
          totals: { sessions: 1, duration_minutes: 45.5, distance_meters: 8500, energy_kj: 2500 },
          series: [
            {
              bucket: requestedGranularity === 'month' ? '2026-06' : '2026-W23',
              sessions: 1,
              duration_minutes: 45.5,
              distance_meters: 8500,
              energy_kj: 2500,
            },
          ],
          by_activity: [],
        })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await screen.findByRole('button', { name: 'month' })
    await user.click(screen.getByRole('button', { name: 'month' }))
    await waitFor(() => expect(requestedGranularity).toBe('month'))
    expect(screen.getByRole('button', { name: 'month' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders per-type workout counts from a single pass', async () => {
    setupHandlers()
    const base = {
      date: '2026-06-05T07:00:00+08:00',
      duration_minutes: 30,
      avg_heart_rate: 140,
      distance_meters: 5000,
      energy_burned_kj: 1500,
      source_name: 'Apple Watch',
      fingerprint: '0123456789abcdef',
    }
    server.use(
      http.get('/api/dashboard/workouts', () =>
        HttpResponse.json({
          workouts: [
            { ...base, id: 1, activity_type: 'Running' },
            { ...base, id: 2, activity_type: 'Running' },
            { ...base, id: 3, activity_type: 'Cycling' },
          ],
          next_cursor: null,
        }),
      ),
    )
    render(<DashboardView />)
    await screen.findByRole('button', { name: /All 3/ })
    expect(screen.getByRole('button', { name: /Running 2/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cycling 1/ })).toBeInTheDocument()
  })

  it('moves an activity filter into the shared URL and workout request scope', async () => {
    let sawFilteredRequest = false
    setupHandlers()
    server.use(
      http.get('/api/dashboard/workouts', ({ request }) => {
        if (new URL(request.url).searchParams.get('activity_type') === 'Running') {
          sawFilteredRequest = true
        }
        return HttpResponse.json({
          workouts: [
            {
              id: 1,
              activity_type: 'Running',
              date: '2026-06-05T07:00:00+08:00',
              duration_minutes: 45.5,
              avg_heart_rate: 148,
              distance_meters: 8500,
              energy_burned_kj: 2500,
              source_name: 'Apple Watch',
              fingerprint: '0123456789abcdef',
            },
          ],
          next_cursor: null,
        })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: /Running 1/ }))
    await waitFor(() => expect(sawFilteredRequest).toBe(true))
    expect(window.location.search).toContain('activity_type=Running')
  })

  it('renders trend charts after load', async () => {
    setupHandlers()
    render(<DashboardView />)
    await waitFor(() => {
      // ECharts is mocked — we look for the echarts container
      const charts = screen.getAllByTestId('echarts')
      expect(charts.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders capabilities after load', async () => {
    setupHandlers()
    render(<DashboardView />)
    await waitFor(() => {
      expect(screen.getByText(/resting hr/i)).toBeInTheDocument()
    })
  })

  it('labels imported data outside the selected range distinctly', async () => {
    setupHandlers()
    server.use(
      http.get('/api/dashboard/capabilities', () =>
        HttpResponse.json({
          capabilities: [{ name: 'steps', present: false, state: 'out_of_range' }],
        }),
      ),
    )
    render(<DashboardView />)
    expect(await screen.findByText(/steps out of range/i)).toBeInTheDocument()
  })

  it('labels malformed imported metric values distinctly', async () => {
    setupHandlers()
    server.use(
      http.get('/api/dashboard/capabilities', () =>
        HttpResponse.json({
          capabilities: [{ name: 'steps', present: false, state: 'malformed' }],
        }),
      ),
    )
    render(<DashboardView />)
    expect(await screen.findByText(/steps malformed/i)).toBeInTheDocument()
  })

  it('shows local import coverage with the dashboard facts', async () => {
    setupHandlers()
    render(<DashboardView />)
    expect(await screen.findByLabelText('Imported data coverage')).toHaveTextContent(
      '1 Jan 2024 to 31 Dec 2024',
    )
  })

  it('handles empty series gracefully — shows No data', async () => {
    server.use(
      http.get('/api/dashboard/summary', () => HttpResponse.json({ days: [] })),
      http.get('/api/dashboard/workouts', () => HttpResponse.json({ workouts: [] })),
      http.get('/api/dashboard/steps', () => HttpResponse.json(EMPTY_TREND)),
      http.get('/api/dashboard/heart', () => HttpResponse.json({ ...HEART_TREND, series: [] })),
      http.get('/api/dashboard/sleep', () => HttpResponse.json({ ...SLEEP_TREND, series: [] })),
      http.get('/api/dashboard/volume', () =>
        HttpResponse.json({
          granularity: 'week',
          totals: { sessions: 0, duration_minutes: 0, distance_meters: 0, energy_kj: 0 },
          series: [],
          by_activity: [],
        }),
      ),
      http.get('/api/dashboard/capabilities', () => HttpResponse.json({ capabilities: [] })),
    )
    render(<DashboardView />)
    await waitFor(() => {
      const noDataElements = screen.getAllByText('No data')
      expect(noDataElements.length).toBeGreaterThanOrEqual(3)
    })
  })

  it('keeps successful panels visible and offers a retry for a failed panel', async () => {
    setupHandlers()
    server.use(http.get('/api/dashboard/sleep', () => HttpResponse.json({}, { status: 500 })))
    render(<DashboardView />)
    expect((await screen.findAllByText('Running')).length).toBeGreaterThan(0)
    expect(screen.getByText(/Could not load: sleep/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry unavailable panels' })).toBeInTheDocument()
  })

  it('keeps healthy panels visible when one panel fails', async () => {
    setupHandlers()
    server.use(http.get('/api/dashboard/sleep', () => HttpResponse.json({}, { status: 500 })))
    render(<DashboardView />)
    await waitFor(() => {
      expect(screen.getAllByText('Running').length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(1)
  })

  it('restores a URL date scope across panel requests', async () => {
    window.history.replaceState({}, '', '?start=2024-01-01&end=2024-01-31')
    setupHandlers()
    render(<DashboardView />)
    await waitFor(() => {
      expect(screen.getByText('Showing 1 Jan 2024 to 31 Jan 2024')).toBeInTheDocument()
    })
    window.history.replaceState({}, '', '/')
  })

  it('lists locally saved dashboard scopes', async () => {
    setupHandlers()
    server.use(
      http.get('/api/saved-views', () =>
        HttpResponse.json([
          {
            id: 'sv_january',
            title: 'January',
            query: { tab: 'overview', start: '2024-01-01', end: '2024-01-31' },
          },
        ]),
      ),
    )
    render(<DashboardView />)
    expect(await screen.findByRole('button', { name: 'January' })).toBeInTheDocument()
  })

  it('does not let an older scoped response replace a newer saved view', async () => {
    window.history.replaceState({}, '', '?start=2024-01-01&end=2024-01-31')
    setupHandlers()
    let releaseOldSummary: (() => void) | undefined
    server.use(
      http.get('/api/dashboard/summary', ({ request }) => {
        if (new URL(request.url).searchParams.get('start') === '2024-01-01') {
          return new Promise((resolve) => {
            releaseOldSummary = () => resolve(HttpResponse.json({ days: [] }))
          })
        }
        return HttpResponse.json({ days: [] })
      }),
      http.get('/api/saved-views', () =>
        HttpResponse.json([
          {
            id: 'sv_february',
            title: 'February',
            query: { tab: 'overview', start: '2024-02-01', end: '2024-02-29' },
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: 'February' }))
    expect(await screen.findByText('Showing 1 Feb 2024 to 29 Feb 2024')).toBeInTheDocument()
    await act(async () => releaseOldSummary?.())
    expect(screen.getByText('Showing 1 Feb 2024 to 29 Feb 2024')).toBeInTheDocument()
    window.history.replaceState({}, '', '/')
  })

  it('renders measured sleep stages separately from the sleep trend', async () => {
    setupHandlers()
    render(<DashboardView />)
    expect(await screen.findByText('Measured asleep time: 7.5 h')).toBeInTheDocument()
    expect(screen.getByLabelText('Measured sleep stage durations')).toBeInTheDocument()
  })

  it('loads the next cursor page without discarding the first page', async () => {
    setupHandlers()
    server.use(
      http.get('/api/dashboard/workouts', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        if (cursor === 'next-page') {
          return HttpResponse.json({
            workouts: [
              {
                id: 2,
                activity_type: 'Walking',
                date: '2026-06-04T07:00:00+08:00',
                duration_minutes: 30,
                avg_heart_rate: 100,
                distance_meters: 2000,
                energy_burned_kj: 500,
                source_name: 'Apple Watch',
                fingerprint: 'second-fixture',
              },
            ],
            next_cursor: null,
          })
        }
        return HttpResponse.json({
          workouts: [
            {
              id: 1,
              activity_type: 'Running',
              date: '2026-06-05T07:00:00+08:00',
              duration_minutes: 45.5,
              avg_heart_rate: 148,
              distance_meters: 8500,
              energy_burned_kj: 2500,
              source_name: 'Apple Watch',
              fingerprint: 'first-fixture',
            },
          ],
          next_cursor: 'next-page',
        })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: 'Load more workouts' }))
    expect((await screen.findAllByText('Walking')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Running').length).toBeGreaterThanOrEqual(1)
  })

  it('restores a workout detail deep link and returns to its scoped list', async () => {
    window.history.replaceState({}, '', '?tab=workouts&start=2024-01-01&end=2024-01-31&workout=1')
    setupHandlers()
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json({}, { status: 404 })))
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: /back to list/i }))
    expect(await screen.findByText('Showing 1 Jan 2024 to 31 Jan 2024')).toBeInTheDocument()
    expect(window.location.search).not.toContain('workout=1')
    window.history.replaceState({}, '', '/')
  })

  it('adds the selected workout fingerprint to its detail URL', async () => {
    setupHandlers()
    const user = userEvent.setup()
    render(<DashboardView />)
    const runningButtons = await screen.findAllByRole('button', { name: /running/i })
    await user.click(runningButtons.at(-1)!)
    expect(window.location.search).toContain('workout=1')
    expect(window.location.search).toContain('workout_fp=0123456789abcdef')
    window.history.replaceState({}, '', '/')
  })

  it('removes a cleared source filter from the shared URL', async () => {
    setupHandlers()
    server.use(
      http.get('/api/dashboard/workouts', ({ request }) => {
        const source = new URL(request.url).searchParams.get('source')
        const all = [
          {
            id: 1,
            activity_type: 'Running',
            date: '2026-06-05T07:00:00+08:00',
            duration_minutes: 45.5,
            avg_heart_rate: 148,
            distance_meters: 8500,
            energy_burned_kj: 2500,
            source_name: 'Apple Watch',
            fingerprint: '0123456789abcdef',
          },
          {
            id: 2,
            activity_type: 'Cycling',
            date: '2026-06-04T07:00:00+08:00',
            duration_minutes: 60,
            avg_heart_rate: 130,
            distance_meters: 20000,
            energy_burned_kj: 1500,
            source_name: 'Strava',
            fingerprint: 'ffffffffffffffff',
          },
        ]
        const workouts = source ? all.filter((workout) => workout.source_name === source) : all
        return HttpResponse.json({ workouts, next_cursor: null })
      }),
    )
    const user = userEvent.setup()
    render(<DashboardView />)
    const select = await screen.findByLabelText('Filter workouts by source')
    await user.selectOptions(select, 'Strava')
    await waitFor(() => expect(window.location.search).toContain('source=Strava'))
    // Reset to "All sources" — the stale source param must leave the URL.
    await user.selectOptions(select, '')
    await waitFor(() => expect(window.location.search).not.toContain('source='))
    expect(screen.getAllByText('Running').length).toBeGreaterThanOrEqual(1)
    window.history.replaceState({}, '', '/')
  })

  it('removes a cleared activity filter from the shared URL', async () => {
    setupHandlers()
    const user = userEvent.setup()
    render(<DashboardView />)
    const runningButton = await screen.findByRole('button', { name: /Running 1/ })
    await user.click(runningButton)
    await waitFor(() => expect(window.location.search).toContain('activity_type=Running'))
    // Toggle the active pill off — the stale activity param must leave the URL.
    await user.click(screen.getByRole('button', { name: /Running 1/ }))
    await waitFor(() => expect(window.location.search).not.toContain('activity_type='))
    window.history.replaceState({}, '', '/')
  })

  it('shows all sources after a filter reset survives a dashboard remount', async () => {
    setupHandlers()
    server.use(
      http.get('/api/dashboard/workouts', ({ request }) => {
        const source = new URL(request.url).searchParams.get('source')
        const all = [
          {
            id: 1,
            activity_type: 'Running',
            date: '2026-06-05T07:00:00+08:00',
            duration_minutes: 45.5,
            avg_heart_rate: 148,
            distance_meters: 8500,
            energy_burned_kj: 2500,
            source_name: 'Apple Watch',
            fingerprint: '0123456789abcdef',
          },
          {
            id: 2,
            activity_type: 'Cycling',
            date: '2026-06-04T07:00:00+08:00',
            duration_minutes: 60,
            avg_heart_rate: 130,
            distance_meters: 20000,
            energy_burned_kj: 1500,
            source_name: 'Strava',
            fingerprint: 'ffffffffffffffff',
          },
        ]
        const workouts = source ? all.filter((workout) => workout.source_name === source) : all
        return HttpResponse.json({ workouts, next_cursor: null })
      }),
    )
    const user = userEvent.setup()
    const firstView = render(<DashboardView />)
    const select = await screen.findByLabelText('Filter workouts by source')
    await user.selectOptions(select, 'Strava')
    await waitFor(() => expect(window.location.search).toContain('source=Strava'))
    await user.selectOptions(select, '')
    await waitFor(() => expect(window.location.search).not.toContain('source='))
    firstView.unmount()
    // Simulate the Chat → Dashboard round trip: the view re-initializes from the URL.
    render(<DashboardView />)
    const restoredSelect = await screen.findByLabelText('Filter workouts by source')
    await waitFor(() => expect((restoredSelect as HTMLSelectElement).value).toBe(''))
    expect(screen.getAllByText('Running').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Cycling').length).toBeGreaterThanOrEqual(1)
    window.history.replaceState({}, '', '/')
  })
})

describe('App tab navigation', () => {
  it('switches to dashboard view on tab click', async () => {
    setupHandlers()
    const { App } = await import('@/app.tsx')
    // Mock echarts inside the test
    const user = userEvent.setup()
    render(<App />)
    // Initially shows chat view (has 'tti' heading from ChatView)
    expect(screen.getByRole('heading', { name: 'tti' })).toBeInTheDocument()
    // Click dashboard tab
    await user.click(screen.getByRole('button', { name: /dashboard/i }))
    // Loading state appears (dashboard view mounted)
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'tti' })).not.toBeInTheDocument()
    })
  })

  it('keeps the URL tab in sync when switching views', async () => {
    setupHandlers()
    const { App } = await import('@/app.tsx')
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /dashboard/i }))
    await waitFor(() => expect(window.location.search).toContain('tab=dashboard'))
    await user.click(screen.getByRole('button', { name: /chat/i }))
    await waitFor(() => expect(window.location.search).toContain('tab=chat'))
  })
})
