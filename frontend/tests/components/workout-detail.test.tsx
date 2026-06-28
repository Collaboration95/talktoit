import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { WorkoutDetail } from '@/components/workout-detail'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Mock ECharts (used for GPS route scatter map)
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))

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
    server.use(
      http.get('/api/dashboard/workouts/:id', () => new Promise(() => {})),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)
    expect(screen.getByTestId('loading')).toBeInTheDocument()
  })

  it('renders workout metrics after load', async () => {
    server.use(
      http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)),
    )
    const onBack = vi.fn()
    render(<WorkoutDetail workoutId={1} onBack={onBack} />)

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    expect(screen.getByText('45.5 min')).toBeInTheDocument()
    expect(screen.getByText('8.50 km')).toBeInTheDocument()
    expect(screen.getByText('148 bpm')).toBeInTheDocument()
    expect(screen.getByText('178 bpm')).toBeInTheDocument()
  })

  it('renders metadata table', async () => {
    server.use(
      http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('HKWeatherTemperature')).toBeInTheDocument()
      expect(screen.getByText('28 °C')).toBeInTheDocument()
      expect(screen.getByText('HKWorkoutBrandName')).toBeInTheDocument()
    })
  })

  it('does not render GPS map when gps_route is null', async () => {
    server.use(
      http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    // GPS route section should not appear
    expect(screen.queryByText('GPS Route')).not.toBeInTheDocument()
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
        }),
      ),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('GPS Route')).toBeInTheDocument()
    })
  })

  it('calls onBack when back button is clicked', async () => {
    server.use(
      http.get('/api/dashboard/workouts/1', () => HttpResponse.json(MOCK_WORKOUT)),
    )
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
    server.use(
      http.get('/api/dashboard/workouts/1', () => new HttpResponse(null, { status: 404 })),
    )
    render(<WorkoutDetail workoutId={1} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument()
    })
  })
})
