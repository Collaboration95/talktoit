interface SeedPromptsProps {
  onSelect: (prompt: string) => void
  disabled: boolean
}

const SEED_QUESTIONS = [
  'Show me my last long run',
  'Which gym session had the highest heart rate last month?',
  'Top 5 longest runs this year',
  'Show my resting heart rate trend this year',
  'How was my training volume last week?',
  'Compare my running this month vs last month',
] as const

/** Clickable example prompt chips for the 6 seed questions. */
export function SeedPrompts({ onSelect, disabled }: SeedPromptsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {SEED_QUESTIONS.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(q)}
          className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 hover:border-blue-400 hover:text-blue-700 disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  )
}
