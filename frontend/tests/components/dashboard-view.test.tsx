import { act, render, screen, waitFor } from '@testing-library/react'
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
  it('shows loading state initially', async () => {
    // Block requests so loading persists
    server.use(
      http.get('/api/dashboard/summary', () => new Promise(() => {})),
      http.get('/api/dashboard/workouts', () => new Promise(() => {})),
      http.get('/api/dashboard/steps', () => new Promise(() => {})),
      http.get('/api/dashboard/heart', () => new Promise(() => {})),
      http.get('/api/dashboard/sleep', () => new Promise(() => {})),
      http.get('/api/dashboard/capabilities', () => new Promise(() => {})),
    )
    render(<DashboardView />)
    expect(screen.getByTestId('loading')).toBeInTheDocument()
    expect(screen.getByText(/loading dashboard/i)).toBeInTheDocument()
    await act(async () => {})
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
      '2024-01-01 to 2024-12-31',
    )
  })

  it('handles empty series gracefully — shows No data', async () => {
    server.use(
      http.get('/api/dashboard/summary', () => HttpResponse.json({ days: [] })),
      http.get('/api/dashboard/workouts', () => HttpResponse.json({ workouts: [] })),
      http.get('/api/dashboard/steps', () => HttpResponse.json(EMPTY_TREND)),
      http.get('/api/dashboard/heart', () => HttpResponse.json({ ...HEART_TREND, series: [] })),
      http.get('/api/dashboard/sleep', () => HttpResponse.json({ ...SLEEP_TREND, series: [] })),
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
      expect(screen.getByText('Showing 2024-01-01 to 2024-01-31')).toBeInTheDocument()
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
    expect(await screen.findByText('Showing 2024-02-01 to 2024-02-29')).toBeInTheDocument()
    await act(async () => releaseOldSummary?.())
    expect(screen.getByText('Showing 2024-02-01 to 2024-02-29')).toBeInTheDocument()
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
    window.history.replaceState(
      {},
      '',
      '?tab=workouts&start=2024-01-01&end=2024-01-31&workout=1',
    )
    setupHandlers()
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json({}, { status: 404 })))
    const user = userEvent.setup()
    render(<DashboardView />)
    await user.click(await screen.findByRole('button', { name: /back to list/i }))
    expect(await screen.findByText('Showing 2024-01-01 to 2024-01-31')).toBeInTheDocument()
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
