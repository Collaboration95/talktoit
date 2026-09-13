import type { ChatEnvelope } from '@/types/templates'
import type {
  WorkoutCardData,
  RankedListData,
  TrendChartData,
  PeriodSummaryData,
  ComparisonData,
  FallbackData,
  FallbackTableRow,
} from '@/types/templates'
import { WorkoutCard } from '@/templates/workout-card'
import { RankedList } from '@/templates/ranked-list'
import { TrendChart } from '@/templates/trend-chart'
import { PeriodSummary } from '@/templates/period-summary'
import { Comparison } from '@/templates/comparison'
import { Fallback } from '@/templates/fallback'

interface TemplateDispatchProps {
  envelope: ChatEnvelope
}

/**
 * Dispatches a ChatEnvelope to the correct template component by template_id.
 * Renders the Fallback template for unknown template_ids.
 */
export function TemplateDispatch({ envelope }: TemplateDispatchProps) {
  const { template_id, data, narrative } = envelope

  const fallback = (message: string, value: unknown = data) => (
    <Fallback data={normalizeFallback(value, message)} narrative={narrative ?? ''} />
  )
  if (!isRecord(data)) return fallback('This answer format is unavailable.')

  switch (template_id) {
    case 'workout_card':
      return hasFields(data, ['activity_type', 'date']) ? (
        <WorkoutCard data={data as unknown as WorkoutCardData} narrative={narrative ?? ''} />
      ) : (
        fallback('This workout answer could not be displayed.')
      )
    case 'ranked_list':
      return hasFields(data, ['title', 'rows']) ? (
        <RankedList data={data as unknown as RankedListData} narrative={narrative ?? ''} />
      ) : (
        fallback('This ranked answer could not be displayed.')
      )
    case 'trend_chart':
      return hasFields(data, ['title', 'series']) ? (
        <TrendChart data={data as unknown as TrendChartData} narrative={narrative ?? ''} />
      ) : (
        fallback('This trend answer could not be displayed.')
      )
    case 'period_summary':
      return hasFields(data, ['title', 'metrics']) ? (
        <PeriodSummary data={data as unknown as PeriodSummaryData} narrative={narrative ?? ''} />
      ) : (
        fallback('This summary answer could not be displayed.')
      )
    case 'comparison':
      return hasFields(data, ['title', 'metrics']) ? (
        <Comparison data={data as unknown as ComparisonData} narrative={narrative ?? ''} />
      ) : (
        fallback('This comparison answer could not be displayed.')
      )
    case 'fallback':
      return <Fallback data={normalizeFallback(data)} narrative={narrative ?? ''} />
    default:
      return fallback(`Unknown template: ${template_id}.`)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasFields(value: Record<string, unknown>, fields: string[]): boolean {
  if (!fields.every((field) => field in value && value[field] !== null)) return false
  for (const field of fields) {
    if (field === 'rows' || field === 'series' || field === 'metrics') {
      const items = value[field]
      if (!Array.isArray(items) || !items.every(isRecord)) return false
    }
  }
  return true
}

function normalizeFallback(value: unknown, message?: string): FallbackData {
  const record = isRecord(value) ? value : {}
  return {
    question: typeof record['question'] === 'string' ? record['question'] : '',
    table: normalizeFallbackTable(record['table']),
    text: typeof record['text'] === 'string' ? record['text'] : null,
    ...(message ? { message } : {}),
  }
}

/** Keep only well-formed key/value rows so a nested row cannot throw on render. */
function normalizeFallbackTable(value: unknown): FallbackTableRow[] | null {
  if (!Array.isArray(value)) return null
  const rows: FallbackTableRow[] = []
  for (const item of value) {
    if (!isRecord(item)) continue
    const key = item['key']
    const rowValue = item['value']
    if (key === undefined || key === null || rowValue === undefined || rowValue === null) continue
    rows.push({ key: String(key), value: String(rowValue) })
  }
  return rows.length > 0 ? rows : null
}
