interface SeedPromptsProps {
  onSelect: (prompt: string) => void
  disabled: boolean
  metricStates?: Record<string, string>
  workoutCount?: number
}

const TRENDS: Record<string, [string, string]> = {
  steps: ['Steps', 'Show my steps trend this year'],
  resting_hr: ['Resting heart rate', 'Show my resting heart rate trend this year'],
  hrv: ['Heart rate variability', 'Show my HRV trend this year'],
  active_energy: ['Active energy', 'Show my active energy trend this year'],
}

/** Offer a small deterministic subset backed by imported metric and workout availability. */
export function SeedPrompts({
  onSelect,
  disabled,
  metricStates = {},
  workoutCount = 0,
}: SeedPromptsProps) {
  const available = Object.entries(TRENDS).filter(([id]) => metricStates[id] === 'available')
  const prompts = available.map(([, [, question]]) => question)
  if (workoutCount > 0)
    prompts.push('Show my last workout', 'How was my training volume last week?')
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500">
        Available:{' '}
        {[...available.map(([, [label]]) => label), ...(workoutCount > 0 ? ['Workouts'] : [])].join(
          ', ',
        ) ||
          'No supported starter questions for this dataset yet. Check available data in Settings.'}
      </p>
      <div className="flex flex-wrap gap-2">
        {prompts.slice(0, 4).map((question) => (
          <button
            key={question}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(question)}
            className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 hover:border-blue-400 hover:text-blue-700 disabled:opacity-50"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  )
}
