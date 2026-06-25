// Envelope
export interface ChatEnvelope {
  template_id: string
  data: unknown
  narrative: string
}

// workout_card (SPEC §2.1)
export interface GpsRoute {
  type: 'LineString'
  coordinates: [number, number][]
}

export interface WorkoutCardData {
  activity_type: string
  date: string // ISO-8601 with timezone
  duration_minutes: number
  avg_heart_rate: number | null
  max_heart_rate: number | null
  distance_meters: number | null
  distance_unit: 'km' | 'm'
  energy_burned_kj: number | null
  elevation_ascent_meters: number | null
  gps_route?: GpsRoute | null // optional: may be absent entirely (SPEC §2.1)
}

// ranked_list (SPEC §2.2)
export interface RankedListRow {
  rank: number
  label: string
  value: number
  unit: string
  secondary_value?: number // absent when no secondary metric
  secondary_unit?: string
}

export interface RankedListData {
  title: string
  rows: RankedListRow[]
}

// trend_chart (SPEC §2.3)
export interface TrendPoint {
  bucket: string
  value: number | null
}

export interface TrendChartData {
  title: string
  metric_label: string
  metric_unit: string
  granularity: 'day' | 'week' | 'month'
  series: TrendPoint[]
}

// period_summary (SPEC §2.4)
export interface PeriodMetric {
  label: string
  value: number | null
  unit: string
}

export interface PeriodSummaryData {
  title: string
  period_start: string
  period_end: string
  metrics: PeriodMetric[]
}

// comparison (SPEC §2.5)
export interface ComparisonMetric {
  label: string
  this_value: number | null
  last_value: number | null
  delta: number | null
  unit: string
  direction: 'up' | 'down' | 'flat'
}

export interface ComparisonData {
  title: string
  this_period_label: string
  last_period_label: string
  metrics: ComparisonMetric[]
}

// fallback (SPEC §2.6)
export interface FallbackTableRow {
  key: string
  value: string
}

export interface FallbackData {
  question: string
  table: FallbackTableRow[] | null
  text: string | null
}
