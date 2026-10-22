import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { WorkoutDetail } from '@/components/workout-detail'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Mock ECharts (used for the local GPS route explorer)
const chartState = vi.hoisted(() => ({ fail: false }))
vi.mock('echarts-for-react', () => ({
  default: () => {
    if (chartState.fail) throw new Error('synthetic route chart failure')
    return <div data-testid="echarts" />
  },
}))
beforeEach(() => {
  chartState.fail = false
})

const MOCK_WORKOUT = {
  id: 1,
  activity_type: 'Running',
  date: '2026-06-05T07:00:00+08:00',
  duration_minutes: 45.5,
  avg_heart_rate: 148,
  max_heart_rate: 178,
  distance_meters: 8500,
  distance_unit: 'km' as const,
  energy_burned_kj: 2500,
  elevation_ascent_meters: 45,
  source_name: 'Apple Watch',
  gps_route: null,
  metadata: [
    { key: 'HKWeatherTemperature', value: '28 °C' },
    { key: 'HKWorkoutBrandName', value: 'Apple Watch' },
  ],
}

describe('WorkoutDetail', () => {
  it('shows loading state initially', () => {
    server.use(http.get('/api/dashboard/workouts/:id', () => new Promise(() => {})))
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)
    expect(screen.getByTestId('loading')).toBeInTheDocument()
  })

  it('renders workout metrics after load', async () => {
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)))
    const onBack = vi.fn()
    render(<WorkoutDetail workoutId={1} onBack={onBack} />)

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    expect(screen.getByText('46 min')).toBeInTheDocument()
    expect(screen.getByText('8.5 km')).toBeInTheDocument()
    expect(screen.getByText('148 bpm')).toBeInTheDocument()
    expect(screen.getByText('178 bpm')).toBeInTheDocument()
  })

  it('renders metadata table', async () => {
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)))
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('HKWeatherTemperature')).toBeInTheDocument()
      expect(screen.getByText('28 °C')).toBeInTheDocument()
      expect(screen.getByText('HKWorkoutBrandName')).toBeInTheDocument()
    })
  })

  it('does not render GPS map when gps_route is null', async () => {
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)))
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    expect(screen.getByText('No route available')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download GeoJSON' })).not.toBeInTheDocument()
  })

  it('renders GPS map when gps_route has coordinates', async () => {
    server.use(
      http.get('/api/dashboard/workouts/1', () =>
        HttpResponse.json({
          ...MOCK_WORKOUT,
          gps_route: {
            type: 'LineString',
            coordinates: [
              [103.8198, 1.3521],
              [103.8204, 1.3532],
            ],
          },
          route_summary: {
            point_count: 2,
            distance_meters: 1200,
            start: [103.8198, 1.3521],
            end: [103.8204, 1.3532],
            bounds: {
              min_longitude: 103.8198,
              min_latitude: 1.3521,
              max_longitude: 103.8204,
              max_latitude: 1.3532,
            },
          },
        }),
      ),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('GPS Route')).toBeInTheDocument()
    })
    expect(screen.getByText('Route points')).toBeInTheDocument()
    expect(screen.getByText('1.2 km')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download GeoJSON' })).toBeInTheDocument()
  })

  it('calls onBack when back button is clicked', async () => {
    server.use(http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)))
    const onBack = vi.fn()
    const user = userEvent.setup()
    render(<WorkoutDetail workoutId={1} onBack={onBack} />)

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    await user.click(screen.getByText('← Back to list'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('shows error state on 404', async () => {
    server.use(http.get('/api/dashboard/workouts/1', () => new HttpResponse(null, { status: 404 })))
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })
})

it('explains an invalid route without offering download or exposing paths', async () => {
  server.use(
    http.get('/api/dashboard/workouts/1', () =>
      HttpResponse.json({ ...MOCK_WORKOUT, route: { state: 'invalid', message: 'unreadable' } }),
    ),
  )
  render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)
  expect(await screen.findByText('Route could not be read')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Download GeoJSON' })).not.toBeInTheDocument()
})

it('keeps route download, metrics and navigation available when its chart fails', async () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    chartState.fail = true
    server.use(
      http.get('/api/dashboard/workouts/1', () =>
        HttpResponse.json({
          ...MOCK_WORKOUT,
          gps_route: {
            type: 'LineString',
            coordinates: [
              [103.8, 1.3],
              [103.81, 1.31],
            ],
          },
        }),
      ),
    )
    const user = userEvent.setup()
    const onBack = vi.fn()
    render(<WorkoutDetail workoutId={1} onBack={onBack} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Chart could not be loaded.')
    expect(screen.getByText('46 min')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download GeoJSON' })).toBeEnabled()
    chartState.fail = false
    await user.click(screen.getByRole('button', { name: 'Retry chart' }))
    expect(await screen.findByTestId('echarts')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Back to list/ }))
    expect(onBack).toHaveBeenCalledOnce()
  } finally {
    chartState.fail = false
    errors.mockRestore()
  }
})
