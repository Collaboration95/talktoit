import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { clearScope, fetchSettings } from '@/api/settings'
import type { ClearScope, DatasetVersion, ProviderMode, Settings } from '@/api/settings'
import { formatDateOnly, formatNumber } from '@/lib/format'

type LoadState = 'loading' | 'ready' | 'error'

const SCOPE_LABELS: Record<ClearScope, string> = {
  cache: 'Response cache',
  history: 'Chat history',
  diagnostics: 'Diagnostics events',
  health: 'Imported health data',
}

const SORTED_SCOPES: ClearScope[] = ['cache', 'history', 'diagnostics', 'health']

function bytesLabel(bytes: number): string {
  if (bytes <= 0) return '—'
  if (bytes < 1024) return `${formatNumber(bytes)} B`
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024)} KB`
  return `${formatNumber(bytes / (1024 * 1024))} MB`
}

function modeLabel(mode: ProviderMode): string {
  switch (mode) {
    case 'local_only':
      return 'Local only — no network egress'
    case 'remote_planning':
      return 'Remote question planning'
    case 'remote_planning_and_narration':
      return 'Remote planning + narration'
    default:
      return mode
  }
}

export function SettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<ClearScope | null>(null)
  const [busyScope, setBusyScope] = useState<ClearScope | null>(null)

  async function load() {
    setState('loading')
    setError(null)
    try {
      const data = await fetchSettings()
      setSettings(data)
      setState('ready')
    } catch (err) {
      setState('error')
      setError(err instanceof Error ? err.message : 'Could not load settings')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function handleClear(scope: ClearScope) {
    if (confirming !== scope) {
      setConfirming(scope)
      return
    }
    setBusyScope(scope)
    setConfirming(null)
    try {
      await clearScope(scope)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not clear ${SCOPE_LABELS[scope]}`)
    } finally {
      setBusyScope(null)
    }
  }

  if (state === 'loading') {
    return <p className="text-sm text-gray-400 py-4">Loading settings…</p>
  }

  if (state === 'error' || !settings) {
    return <p className="text-sm text-red-600 py-4">{error ?? 'Settings are unavailable.'}</p>
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Settings & data controls</h2>
        <p className="text-sm text-gray-500">
          Read-only service state, plus destructive actions that are always explicitly scoped and
          require confirmation.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Section title="Dataset">
        {settings.dataset ? (
          <DatasetCard dataset={settings.dataset} />
        ) : (
          <p className="text-sm text-gray-400">No health dataset has been imported yet.</p>
        )}
      </Section>

      <Section title="Privacy">
        <dl className="space-y-2 text-sm text-gray-700">
          <Row label="Provider mode">
            <span className="font-medium">{modeLabel(settings.provider.mode)}</span>
          </Row>
          {settings.provider.model && <Row label="Model">{settings.provider.model}</Row>}
          <Row label="Network egress">
            {settings.provider.egress_categories.length
              ? settings.provider.egress_categories.join('; ')
              : 'None — everything stays on this device'}
          </Row>
        </dl>
      </Section>

      <Section title="Storage">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-700 sm:grid-cols-3">
          <Row label="App state">
            <span className="font-medium">{bytesLabel(settings.storage.app_state_bytes)}</span>
          </Row>
          <Row label="Health database">
            <span className="font-medium">{bytesLabel(settings.storage.health_db_bytes)}</span>
          </Row>
          <Row label="Cached answers">
            <span className="font-medium">
              {settings.storage.cache.entries} entries ({bytesLabel(settings.storage.cache.bytes)})
            </span>
          </Row>
          <Row label="Conversations">
            <span className="font-medium">{formatNumber(settings.storage.conversations)}</span>
          </Row>
          <Row label="Saved views">
            <span className="font-medium">{formatNumber(settings.storage.saved_views)}</span>
          </Row>
          <Row label="Diagnostics events">
            <span className="font-medium">{formatNumber(settings.storage.diagnostics_events)}</span>
          </Row>
        </dl>
      </Section>

      <Section title="Data quality">
        {settings.quality.active ? (
          <>
            <p className="text-sm text-gray-700">
              {formatDateOnly(settings.quality.coverage_start ?? '')} →{' '}
              {formatDateOnly(settings.quality.coverage_end ?? '')}
              {' · '}
              {settings.quality.schema_version ?? 'unknown'} schema
            </p>
            <Metric states={settings.quality.metric_states} />
          </>
        ) : (
          <p className="text-sm text-gray-400">No data to report yet.</p>
        )}
      </Section>

      <Section title="Clear data">
        <p className="mb-3 text-sm text-gray-500">
          Each action only removes its named scope. Imported health data is never removed by the
          other clear actions.
        </p>
        <div className="space-y-2">
          {SORTED_SCOPES.map((scope) => (
            <button
              key={scope}
              type="button"
              onClick={() => void handleClear(scope)}
              disabled={busyScope === scope}
              className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                scope === 'health'
                  ? 'border-red-200 bg-white text-red-600 hover:bg-red-50'
                  : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              {confirming === scope
                ? `Confirm: clear ${SCOPE_LABELS[scope].toLowerCase()}?`
                : busyScope === scope
                  ? 'Working…'
                  : `Clear ${SCOPE_LABELS[scope].toLowerCase()}`}
            </button>
          ))}
        </div>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h3 className="mb-2 text-sm font-medium text-gray-700">{title}</h3>
      <div className="rounded-md border border-gray-200 bg-white p-4">{children}</div>
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
      <dt className="min-w-40 text-xs uppercase tracking-wide text-gray-400">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function DatasetCard({ dataset }: { dataset: DatasetVersion }) {
  return (
    <dl className="space-y-1 text-sm text-gray-700">
      <Row label="Imported">{formatDateOnly(dataset.imported_at)}</Row>
      <Row label="Parser">
        <span className="font-medium">{dataset.parser_version}</span>
      </Row>
      <Row label="Records">
        <span className="font-medium">{formatNumber(dataset.counts['records'] ?? 0)} records</span>
      </Row>
      {dataset.warnings.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wide text-amber-600">Warnings</p>
          <ul className="mt-1 list-disc pl-5 text-xs text-gray-500">
            {dataset.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </dl>
  )
}

function Metric({ states }: { states: Record<string, string> }) {
  const available = Object.values(states).filter((state) => state === 'available').length
  const outOfRange = Object.values(states).filter((state) => state === 'out_of_range').length
  return (
    <p className="mt-2 text-sm text-gray-600">
      <span className="font-medium text-gray-800">{available}</span> available ·{' '}
      <span className="font-medium text-gray-800">{outOfRange}</span> out of range ·{' '}
      <span className="font-medium text-gray-800">{formatNumber(Object.keys(states).length)}</span>{' '}
      tracked metrics
    </p>
  )
}
