import { useEffect, useState } from 'react'
import type { DashboardScope } from '@/api/dashboard'
import { isValidDateOnly, shiftDateOnly } from '@/lib/format'

export interface DashboardCoverage {
  start: string
  end: string
}

/** Dataset-anchored presets and draft dates; only validated periods change requests. */
export function DashboardPeriodControls({
  scope,
  coverage,
  loading,
  onChange,
}: {
  scope: DashboardScope
  coverage: DashboardCoverage | null
  loading: boolean
  onChange: (scope: DashboardScope) => void
}) {
  const [start, setStart] = useState(scope.start ?? '')
  const [end, setEnd] = useState(scope.end ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setStart(scope.start ?? '')
    setEnd(scope.end ?? '')
    setError(null)
  }, [scope.start, scope.end])

  return (
    <div className="space-y-2" aria-label="Dashboard period">
      <fieldset disabled={!coverage} className="flex flex-wrap gap-2">
        <legend className="mb-2 text-sm font-medium text-gray-700">Period</legend>
        {([7, 30, 'all'] as const).map((days) => (
          <button
            key={days}
            type="button"
            className="rounded border border-gray-300 px-2 py-1 text-sm disabled:opacity-50"
            onClick={() => {
              if (!coverage) return
              onChange({
                ...scope,
                start: days === 'all' ? coverage.start : shiftDateOnly(coverage.end, 1 - days),
                end: coverage.end,
              })
            }}
          >
            {days === 'all' ? 'All available data' : `Latest ${days} data days`}
          </button>
        ))}
      </fieldset>
      {!coverage ? (
        <p className="text-sm text-gray-500" role="status">
          {loading
            ? 'Loading imported coverage…'
            : 'Import data to choose a period. Coverage is unavailable.'}
        </p>
      ) : null}
      <form
        noValidate
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (!isValidDateOnly(start) || !isValidDateOnly(end)) {
            setError('Enter valid calendar dates in YYYY-MM-DD format.')
            return
          }
          if (start > end) {
            setError('The start date must be on or before the end date.')
            return
          }
          setError(null)
          onChange({ ...scope, start, end })
        }}
      >
        <label className="text-sm text-gray-600">
          Start
          <input
            aria-label="Period start"
            placeholder="YYYY-MM-DD"
            type="text"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="ml-2 w-32 rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <label className="text-sm text-gray-600">
          End
          <input
            aria-label="Period end"
            placeholder="YYYY-MM-DD"
            type="text"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="ml-2 w-32 rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <button type="submit" className="rounded border border-gray-300 px-2 py-1 text-sm">
          Apply custom period
        </button>
        {error ? (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        ) : null}
      </form>
    </div>
  )
}
