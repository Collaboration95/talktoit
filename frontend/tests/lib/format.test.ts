import { formatDateOnly, formatDateTime, formatDurationMinutes, formatMetricValue } from '@/lib/format'

describe('format helpers', () => {
  it('rounds duration to whole minutes', () => {
    expect(formatDurationMinutes(61.051)).toBe('61 min')
  })

  it('formats metric values with unit-aware precision', () => {
    expect(formatMetricValue(26.46694, 'km')).toBe('26.5 km')
    expect(formatMetricValue(2688.8378, 'kJ')).toBe('2,689 kJ')
  })

  it('formats dates in Singapore time', () => {
    expect(formatDateOnly('2026-06-08')).toContain('2026')
    expect(formatDateTime('2026-06-08T20:08:48+08:00')).toContain('2026')
  })
})
