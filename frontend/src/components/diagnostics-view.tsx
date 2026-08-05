import { useEffect, useState } from 'react'
import type {
  DiagnosticsCategory,
  DiagnosticsEventsResponse,
  DiagnosticsSummary,
} from '@/api/diagnostics'
import {
  clearDiagnostics,
  exportDiagnostics,
  fetchDiagnosticsEvents,
  fetchDiagnosticsSummary,
} from '@/api/diagnostics'
import { formatNumber } from '@/lib/format'

const CATEGORY_LABELS: Record<DiagnosticsCategory, string> = {
  import: 'Import pipeline',
  query: 'Local queries',
  chat: 'Chat requests',
  planner: 'Question planning',
  narrator: 'Narrative writing',
  panel: 'Dashboard panels',
  app: 'Application lifecycle',
  benchmark: 'Performance benchmarks',
}

type LoadState = 'loading' | 'ready' | 'error'

function durationLabel(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? '—' : `${formatNumber(ms)} ms`
}

export function DiagnosticsView() {
  const [summary, setSummary] = useState<DiagnosticsSummary | null>(null)
  const [events, setEvents] = useState<DiagnosticsEventsResponse | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)
  const [confirmingClear, setConfirmingClear] = useState(false)
  const [exported, setExported] = useState<string | null>(null)

  async function load() {
    setState('loading')
    setError(null)
    try {
      const [summaryData, eventsData] = await Promise.all([
        fetchDiagnosticsSummary(),
        fetchDiagnosticsEvents(undefined, 50),
      ])
      setSummary(summaryData)
      setEvents(eventsData)
      setState('ready')
    } catch (err) {
      setState('error')
      setError(err instanceof Error ? err.message : 'Could not load diagnostics')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleClear() {
    if (!confirmingClear) {
      setConfirmingClear(true)
      return
    }
    setClearing(true)
    try {
      await clearDiagnostics()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not clear diagnostics')
    } finally {
      setClearing(false)
      setConfirmingClear(false)
    }
  }

  async function handleExport() {
    setExported(null)
    try {
      const payload = await exportDiagnostics()
      setExported(JSON.stringify(payload.export, null, 2))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export diagnostics')
    }
  }

  if (state === 'loading') {
    return <p className="text-sm text-gray-400 py-4">Loading local diagnostics…</p>
  }

  if (state === 'error' || !summary) {
    return <p className="text-sm text-red-600 py-4">{error ?? 'Diagnostics are unavailable.'}</p>
  }

  const categories = Object.keys(summary.by_category) as DiagnosticsCategory[]
  const categoriesList = categories.length
    ? categories
    : (Object.keys(CATEGORY_LABELS) as DiagnosticsCategory[])

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Local diagnostics</h2>
        <p className="text-sm text-gray-500">
          Performance and reliability events stored on this device. No question text, health values,
          routes, or files are recorded.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Events recorded" value={formatNumber(summary.total_events)} />
        <StatCard
          label="Cache hit rate"
          value={
            summary.cache.hit_rate === null ? '—' : `${formatNumber(summary.cache.hit_rate * 100)}%`
          }
        />
        <StatCard label="Cache hits" value={formatNumber(summary.cache.hits)} />
        <StatCard label="Cache misses" value={formatNumber(summary.cache.misses)} />
      </div>

      <section aria-label="Average latency by area">
        <h3 className="mb-2 text-sm font-medium text-gray-700">Average latency by area</h3>
        <div className="overflow-hidden rounded-md border border-gray-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2 font-medium">Area</th>
                <th className="px-3 py-2 font-medium">Events</th>
                <th className="px-3 py-2 font-medium">Mean</th>
                <th className="px-3 py-2 font-medium">p95</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {categoriesList.map((category) => {
                const stats = summary.by_category[category]
                return (
                  <tr key={category} className="text-gray-700">
                    <td className="px-3 py-2">{CATEGORY_LABELS[category] ?? category}</td>
                    <td className="px-3 py-2">{stats ? formatNumber(stats.count) : '0'}</td>
                    <td className="px-3 py-2">{durationLabel(stats?.mean_duration_ms)}</td>
                    <td className="px-3 py-2">{durationLabel(stats?.p95_duration_ms)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-label="Recent local events">
        <h3 className="mb-2 text-sm font-medium text-gray-700">Recent events</h3>
        <div className="overflow-hidden rounded-md border border-gray-200">
          {events && events.events.length > 0 ? (
            <table className="w-full text-left text-sm">
              <tbody className="divide-y divide-gray-100">
                {events.events.map((event) => (
                  <tr key={event.id} className="text-gray-700">
                    <td className="px-3 py-2 font-medium">
                      {CATEGORY_LABELS[event.category as DiagnosticsCategory] ?? event.category}
                    </td>
                    <td className="px-3 py-2">{event.name}</td>
                    <td className="px-3 py-2">{durationLabel(event.duration_ms)}</td>
                    <td className="px-3 py-2 text-xs text-gray-400">{event.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="px-3 py-4 text-sm text-gray-400">No events recorded yet.</p>
          )}
        </div>
      </section>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleClear}
          disabled={clearing}
          className="rounded-md border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
        >
          {confirmingClear
            ? 'Confirm: clear diagnostics?'
            : clearing
              ? 'Clearing…'
              : 'Clear diagnostics'}
        </button>
        <button
          type="button"
          onClick={handleExport}
          className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Export redacted JSON
        </button>
      </div>

      {exported && (
        <pre className="max-h-64 overflow-auto rounded-md bg-gray-900 p-3 text-xs text-green-100">
          {exported}
        </pre>
      )}
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-gray-200 bg-white p-3">
      <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-1 text-xl font-semibold text-gray-800">{value}</p>
    </div>
  )
}
