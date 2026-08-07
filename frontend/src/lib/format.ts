const HEALTH_TIME_ZONE = 'Asia/Singapore'
const HEALTH_LOCALE = 'en-SG'

/** Return a cached value, building and caching it on first request. */
function cached<K, T>(cache: Map<K, T>, key: K, make: () => T): T {
  const hit = cache.get(key)
  if (hit) return hit
  const value = make()
  cache.set(key, value)
  return value
}

// Intl construction is comparatively expensive and chart label loops call these
// once per bucket per render. Memoize by the exact options that change output.
const _numberFormatCache = new Map<number, Intl.NumberFormat>()
const _dateTimeCache = new Map<string, Intl.DateTimeFormat>()
const _mediumDateCache = new Map<string, Intl.DateTimeFormat>()
const _monthPartsCache = new Map<string, Intl.DateTimeFormat>()
const _monthDayPartsCache = new Map<string, Intl.DateTimeFormat>()

function createNumberFormatter(fractionDigits: number): Intl.NumberFormat {
  return cached(
    _numberFormatCache,
    fractionDigits,
    () =>
      new Intl.NumberFormat(HEALTH_LOCALE, {
        maximumFractionDigits: fractionDigits,
        minimumFractionDigits: 0,
      }),
  )
}

export function formatNumber(value: number, fractionDigits = 0): string {
  return createNumberFormatter(fractionDigits).format(value)
}

export function formatMetricValue(value: number | null, unit: string): string | null {
  if (value === null) return null
  return `${formatNumber(value, unit === 'km' ? 1 : 0)} ${unit}`
}

export function formatSignedMetricValue(value: number | null, unit: string): string {
  if (value === null) return '—'
  const magnitude = formatNumber(Math.abs(value), unit === 'km' ? 1 : 0)
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  return `${sign}${magnitude} ${unit}`
}

export function formatDistanceKm(distanceMeters: number | null): string | null {
  if (distanceMeters === null) return null
  return `${formatNumber(distanceMeters / 1000, 1)} km`
}

export function formatDurationMinutes(minutes: number | null): string | null {
  if (minutes === null) return null
  return `${formatNumber(minutes, 0)} min`
}

function mediumDateFormatter(): Intl.DateTimeFormat {
  return cached(
    _mediumDateCache,
    'medium',
    () =>
      new Intl.DateTimeFormat(HEALTH_LOCALE, {
        dateStyle: 'medium',
        timeZone: HEALTH_TIME_ZONE,
      }),
  )
}

export function formatDateTime(isoDateTime: string): string {
  return cached(
    _dateTimeCache,
    'medium+short',
    () =>
      new Intl.DateTimeFormat(HEALTH_LOCALE, {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: HEALTH_TIME_ZONE,
      }),
  ).format(new Date(isoDateTime))
}

export function formatDateOnly(isoDate: string): string {
  return mediumDateFormatter().format(new Date(`${isoDate.slice(0, 10)}T12:00:00+08:00`))
}

export function formatDateRange(startDate: string, endDate: string): string {
  return `${formatDateOnly(startDate)} to ${formatDateOnly(endDate)}`
}

const ISO_DAY_BUCKET = /^\d{4}-\d{2}-\d{2}$/
const ISO_MONTH_BUCKET = /^\d{4}-\d{2}$/
const ISO_WEEK_BUCKET = /^(\d{4})-W(\d{2})$/

/** Monday of an ISO week bucket like `2026-W23`, as a UTC-date instant. */
function isoWeekMonday(isoWeek: string): Date {
  const match = ISO_WEEK_BUCKET.exec(isoWeek)
  if (!match) return new Date(Number.NaN)
  const year = Number(match[1])
  const week = Number(match[2])
  // ISO week 1 contains January 4; snap to its Monday, then advance by weeks.
  const jan4 = Date.UTC(year, 0, 4)
  const jan4Dow = (new Date(jan4).getUTCDay() + 6) % 7
  const mondayOfWeek1 = jan4 - jan4Dow * 86_400_000
  return new Date(mondayOfWeek1 + (week - 1) * 7 * 86_400_000)
}

function parseBucketDate(bucket: string): Date | null {
  if (ISO_DAY_BUCKET.test(bucket)) return new Date(`${bucket}T12:00:00+08:00`)
  if (ISO_MONTH_BUCKET.test(bucket)) return new Date(`${bucket}-01T12:00:00+08:00`)
  if (ISO_WEEK_BUCKET.test(bucket)) return isoWeekMonday(bucket)
  return null
}

function monthPartsFormatter(includeYear: boolean): Intl.DateTimeFormat {
  return cached(
    _monthPartsCache,
    includeYear ? 'yr' : 'no',
    () =>
      new Intl.DateTimeFormat('en-US', {
        month: 'short',
        ...(includeYear ? { year: '2-digit' } : {}),
        timeZone: HEALTH_TIME_ZONE,
      }),
  )
}

function formatMonthCompact(date: Date, includeYear: boolean): string {
  const parts = monthPartsFormatter(includeYear).formatToParts(date)
  const month = parts.find((part) => part.type === 'month')?.value ?? ''
  const year = parts.find((part) => part.type === 'year')?.value ?? ''
  return includeYear ? `${month} '${year}` : month
}

function monthDayPartsFormatter(includeYear: boolean): Intl.DateTimeFormat {
  return cached(
    _monthDayPartsCache,
    includeYear ? 'yr' : 'no',
    () =>
      new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        ...(includeYear ? { year: '2-digit' } : {}),
        timeZone: HEALTH_TIME_ZONE,
      }),
  )
}

function formatMonthDayCompact(date: Date, includeYear: boolean): string {
  const parts = monthDayPartsFormatter(includeYear).formatToParts(date)
  const month = parts.find((part) => part.type === 'month')?.value ?? ''
  const day = parts.find((part) => part.type === 'day')?.value ?? ''
  const year = parts.find((part) => part.type === 'year')?.value ?? ''
  return includeYear ? `${month} ${day} '${year}` : `${month} ${day}`
}

/**
 * Compact x-axis label for a trend bucket, e.g. `2026-08-23` → `Aug 23`,
 * `2026-W23` → `Jun 1` (that week's Monday), `2026-06` → `Jun`. Set
 * `includeYear` to disambiguate ranges that span calendar years.
 */
export function formatBucketLabel(bucket: string, options: { includeYear?: boolean } = {}): string {
  const includeYear = options.includeYear ?? false
  const date = parseBucketDate(bucket)
  if (!date || Number.isNaN(date.getTime())) return bucket
  if (ISO_MONTH_BUCKET.test(bucket)) return formatMonthCompact(date, includeYear)
  return formatMonthDayCompact(date, includeYear)
}

/** Full readable date for a trend bucket, e.g. `2026-08-23` → `23 Aug 2026`. */
export function formatChartBucketFullDate(bucket: string): string {
  const date = parseBucketDate(bucket)
  if (!date || Number.isNaN(date.getTime())) return bucket
  return mediumDateFormatter().format(date)
}
