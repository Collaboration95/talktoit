const HEALTH_TIME_ZONE = 'Asia/Singapore'
const HEALTH_LOCALE = 'en-SG'

function createNumberFormatter(fractionDigits: number): Intl.NumberFormat {
  return new Intl.NumberFormat(HEALTH_LOCALE, {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: 0,
  })
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

export function formatDateTime(isoDateTime: string): string {
  return new Intl.DateTimeFormat(HEALTH_LOCALE, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: HEALTH_TIME_ZONE,
  }).format(new Date(isoDateTime))
}

export function formatDateOnly(isoDate: string): string {
  return new Intl.DateTimeFormat(HEALTH_LOCALE, {
    dateStyle: 'medium',
    timeZone: HEALTH_TIME_ZONE,
  }).format(new Date(`${isoDate.slice(0, 10)}T12:00:00+08:00`))
}

export function formatDateRange(startDate: string, endDate: string): string {
  return `${formatDateOnly(startDate)} to ${formatDateOnly(endDate)}`
}
