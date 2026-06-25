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

  switch (template_id) {
    case 'workout_card':
      return <WorkoutCard data={data as WorkoutCardData} narrative={narrative} />
    case 'ranked_list':
      return <RankedList data={data as RankedListData} narrative={narrative} />
    case 'trend_chart':
      return <TrendChart data={data as TrendChartData} narrative={narrative} />
    case 'period_summary':
      return <PeriodSummary data={data as PeriodSummaryData} narrative={narrative} />
    case 'comparison':
      return <Comparison data={data as ComparisonData} narrative={narrative} />
    case 'fallback':
    default:
      return (
        <Fallback
          data={
            template_id === 'fallback'
              ? (data as FallbackData)
              : { question: 'Unknown', table: null, text: `Unknown template: ${template_id}` }
          }
          narrative={narrative}
        />
      )
  }
}
