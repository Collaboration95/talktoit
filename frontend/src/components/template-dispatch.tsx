import type { ChatEnvelope } from '@/types/templates'
import type {
  WorkoutCardData,
  RankedListData,
  TrendChartData,
  PeriodSummaryData,
  ComparisonData,
  FallbackData,
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
    table: Array.isArray(record['table']) ? (record['table'] as FallbackData['table']) : null,
    text: typeof record['text'] === 'string' ? record['text'] : null,
    ...(message ? { message } : {}),
  }
}
