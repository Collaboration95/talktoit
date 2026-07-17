import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DashboardView } from '@/components/dashboard-view'
import type { TrendResponse } from '@/api/dashboard'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
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
          },
        ],
      }),
    ),
    http.get('/api/dashboard/steps', () => HttpResponse.json(STEPS_TREND)),
    http.get('/api/dashboard/heart', () => HttpResponse.json(HEART_TREND)),
    http.get('/api/dashboard/sleep', () => HttpResponse.json(SLEEP_TREND)),
    http.get('/api/dashboard/capabilities', () =>
      HttpResponse.json({
        capabilities: [
          { name: 'resting_hr', present: true },
          { name: 'steps', present: true },
          { name: 'sleep', present: true },
          { name: 'hrv', present: true },
          { name: 'workouts', present: true },
        ],
      }),
    ),
  )
}

describe('DashboardView', () => {
  it('shows loading state initially', () => {
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
})
