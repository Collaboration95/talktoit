import {
  formatBucketLabel,
  formatChartBucketFullDate,
  formatDateOnly,
  formatDateTime,
  formatDurationMinutes,
  formatMetricValue,
} from '@/lib/format'

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

describe('trend bucket labels', () => {
  it('formats day buckets as compact month-day labels', () => {
    expect(formatBucketLabel('2026-08-23')).toBe('Aug 23')
    expect(formatBucketLabel('2026-08-23', { includeYear: true })).toBe("Aug 23 '26")
  })

  it('formats week buckets as their Monday date', () => {
    expect(formatBucketLabel('2026-W23')).toBe('Jun 1')
    expect(formatBucketLabel('2026-W23', { includeYear: true })).toBe("Jun 1 '26")
  })

  it('formats month buckets as month names', () => {
    expect(formatBucketLabel('2026-06')).toBe('Jun')
    expect(formatBucketLabel('2026-06', { includeYear: true })).toBe("Jun '26")
  })

  it('formats full bucket dates for tooltips', () => {
    expect(formatChartBucketFullDate('2026-08-23')).toBe('23 Aug 2026')
    expect(formatChartBucketFullDate('2026-W23')).toBe('1 Jun 2026')
    expect(formatChartBucketFullDate('2026-06')).toBe('1 Jun 2026')
  })

  it('passes through unrecognized labels unchanged', () => {
    expect(formatBucketLabel('not-a-bucket')).toBe('not-a-bucket')
    expect(formatBucketLabel('2026-6-1')).toBe('2026-6-1')
    expect(formatChartBucketFullDate('not-a-bucket')).toBe('not-a-bucket')
  })

  it('disambiguates week buckets across an ISO year boundary', () => {
    // ISO 2026-W52 starts 2026-12-21; ISO 2027-W01 starts 2027-01-04.
    expect(formatBucketLabel('2026-W52')).toBe('Dec 21')
    expect(formatBucketLabel('2026-W52', { includeYear: true })).toBe("Dec 21 '26")
    expect(formatBucketLabel('2027-W01')).toBe('Jan 4')
    expect(formatBucketLabel('2027-W01', { includeYear: true })).toBe("Jan 4 '27")
    expect(formatChartBucketFullDate('2026-W52')).toBe('21 Dec 2026')
    expect(formatChartBucketFullDate('2027-W01')).toBe('4 Jan 2027')
  })

  it('disambiguates month and day buckets across a calendar year boundary', () => {
    expect(formatBucketLabel('2026-12', { includeYear: true })).toBe("Dec '26")
    expect(formatBucketLabel('2027-01', { includeYear: true })).toBe("Jan '27")
    expect(formatBucketLabel('2026-12-31', { includeYear: true })).toBe("Dec 31 '26")
    expect(formatBucketLabel('2027-01-01', { includeYear: true })).toBe("Jan 1 '27")
  })

  it('handles sparse and malformed buckets without throwing', () => {
    expect(formatBucketLabel('')).toBe('')
    expect(formatBucketLabel('2026-W')).toBe('2026-W')
    expect(formatBucketLabel(' 2026-08-23')).toBe(' 2026-08-23')
    expect(formatBucketLabel('2026-13-40')).toBe('2026-13-40')
    expect(formatChartBucketFullDate('')).toBe('')
    expect(formatChartBucketFullDate('2026-13-40')).toBe('2026-13-40')
  })
})
