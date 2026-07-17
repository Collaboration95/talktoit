import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { fetchCapabilities, fetchSummary, fetchTrend, fetchWorkouts } from '@/api/dashboard'
import type {
  ActivityRingDay,
  CapabilityFlag,
  TrendResponse,
  WorkoutSummary,
} from '@/api/dashboard'

const server = setupServer()
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const SAMPLE_DAY: ActivityRingDay = {
  date: '2026-06-05',
  energy_kj: 3200,
  energy_goal_kj: 2500,
  exercise_min: 55,
  exercise_goal_min: 30,
  stand_hours: 14,
  stand_goal_hours: 12,
}

const SAMPLE_WORKOUT: WorkoutSummary = {
  id: 1,
  activity_type: 'Running',
  date: '2026-06-05T07:00:00+08:00',
  duration_minutes: 45.5,
  avg_heart_rate: 148,
  distance_meters: 8500,
  energy_burned_kj: 2500,
}

const SAMPLE_TREND: TrendResponse = {
  metric_label: 'Steps',
  metric_unit: 'count',
  granularity: 'day',
  series: [{ bucket: '2026-06-05', value: 12100 }],
}

const SAMPLE_CAPABILITIES: CapabilityFlag[] = [
  { name: 'resting_hr', present: true },
  { name: 'steps', present: true },
]

describe('fetchSummary', () => {
  it('returns activity ring days', async () => {
    server.use(http.get('/api/dashboard/summary', () => HttpResponse.json({ days: [SAMPLE_DAY] })))
    const result = await fetchSummary()
    expect(result).toHaveLength(1)
    expect(result[0].date).toBe('2026-06-05')
    expect(result[0].energy_kj).toBe(3200)
  })
})

describe('fetchWorkouts', () => {
  it('returns workout summaries', async () => {
    server.use(
      http.get('/api/dashboard/workouts', () => HttpResponse.json({ workouts: [SAMPLE_WORKOUT] })),
    )
    const result = await fetchWorkouts()
    expect(result).toHaveLength(1)
    expect(result[0].activity_type).toBe('Running')
    expect(result[0].avg_heart_rate).toBe(148)
  })
})

describe('fetchTrend', () => {
  it('returns trend response for steps', async () => {
    server.use(http.get('/api/dashboard/steps', () => HttpResponse.json(SAMPLE_TREND)))
    const result = await fetchTrend('steps', 'day')
    expect(result.metric_label).toBe('Steps')
    expect(result.series).toHaveLength(1)
    expect(result.series[0].value).toBe(12100)
  })

  it('returns trend response for heart', async () => {
    const heartTrend: TrendResponse = {
      ...SAMPLE_TREND,
      metric_label: 'Resting HR',
      metric_unit: 'bpm',
    }
    server.use(http.get('/api/dashboard/heart', () => HttpResponse.json(heartTrend)))
    const result = await fetchTrend('heart', 'week')
    expect(result.metric_label).toBe('Resting HR')
  })

  it('returns trend response for sleep', async () => {
    const sleepTrend: TrendResponse = {
      ...SAMPLE_TREND,
      metric_label: 'Sleep',
      metric_unit: 'hours',
    }
    server.use(http.get('/api/dashboard/sleep', () => HttpResponse.json(sleepTrend)))
    const result = await fetchTrend('sleep', 'day')
    expect(result.metric_label).toBe('Sleep')
  })
})

describe('fetchCapabilities', () => {
  it('returns capability flags', async () => {
    server.use(
      http.get('/api/dashboard/capabilities', () =>
        HttpResponse.json({ capabilities: SAMPLE_CAPABILITIES }),
      ),
    )
    const result = await fetchCapabilities()
    expect(result).toHaveLength(2)
    expect(result[0].name).toBe('resting_hr')
    expect(result[0].present).toBe(true)
  })
})
