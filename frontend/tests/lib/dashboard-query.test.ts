import { decodeDashboardQuery, encodeDashboardQuery } from '@/lib/dashboard-query'

describe('dashboard URL query', () => {
  it('round-trips a scoped workout detail state', () => {
    const query = {
      tab: 'workouts' as const,
      start: '2024-01-01',
      end: '2024-01-31',
      activityType: 'HKWorkoutActivityTypeRunning',
      source: 'Apple Watch',
      selectedWorkout: 42,
    }
    expect(decodeDashboardQuery(encodeDashboardQuery(query))).toEqual(query)
  })

  it('falls back safely for invalid scope values', () => {
    expect(decodeDashboardQuery('?tab=unknown&start=nope&end=2024-01-01&workout=-1')).toEqual({ tab: 'overview' })
  })
})
