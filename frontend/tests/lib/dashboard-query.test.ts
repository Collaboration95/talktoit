import { decodeDashboardQuery, encodeDashboardQuery } from '@/lib/dashboard-query'

describe('dashboard URL query', () => {
  it.each(['2024-02-30', '2023-02-29', '2024-13-01', '0000-01-01'])(
    'rejects impossible calendar date %s on decode and encode',
    (start) => {
      expect(decodeDashboardQuery(`?start=${start}&end=2025-01-01`)).toEqual({ tab: 'overview' })
      expect(encodeDashboardQuery({ tab: 'overview', start, end: '2025-01-01' })).toBe(
        'tab=overview',
      )
    },
  )

  it('round-trips a scoped workout detail state', () => {
    const query = {
      tab: 'workouts' as const,
      start: '2024-01-01',
      end: '2024-01-31',
      activityType: 'HKWorkoutActivityTypeRunning',
      source: 'Apple Watch',
      selectedWorkout: 42,
      selectedWorkoutFingerprint: '0000000000000000',
    }
    expect(decodeDashboardQuery(encodeDashboardQuery(query))).toEqual(query)
  })

  it('falls back safely for invalid scope values', () => {
    expect(decodeDashboardQuery('?tab=unknown&start=nope&end=2024-01-01&workout=-1')).toEqual({
      tab: 'overview',
    })
  })

  it('rejects control characters in shared text filters', () => {
    expect(decodeDashboardQuery('?activity_type=Running%0AInjected&source=Watch')).toEqual({
      tab: 'overview',
      source: 'Watch',
    })
  })
})
