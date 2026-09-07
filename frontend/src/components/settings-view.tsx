import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  clearScope,
  fetchSettings,
  startLocalLlm,
  stopLocalLlm,
  updateProvider,
} from '@/api/settings'
import type {
  ClearScope,
  DatasetVersion,
  ProviderMode,
  ProviderType,
  Settings,
} from '@/api/settings'
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

function providerLabel(provider: ProviderType | string | undefined): string {
  switch (provider) {
    case 'local':
      return 'Local — LiteRT-LM (offline)'
    case 'groq':
      return 'Groq — hosted'
    default:
      return provider ?? 'Unknown'
  }
}

export function SettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<ClearScope | null>(null)
  const [busyScope, setBusyScope] = useState<ClearScope | null>(null)

  // Provider form state — mirrors the persisted config for live editing.
  const [provider, setProvider] = useState<ProviderType>('groq')
  const [mode, setMode] = useState<ProviderMode>('local_only')
  const [groqModel, setGroqModel] = useState('')
  const [groqBaseUrl, setGroqBaseUrl] = useState('')
  const [litertModel, setLitertModel] = useState('')
  const [litertBaseUrl, setLitertBaseUrl] = useState('')
  const [providerSaving, setProviderSaving] = useState(false)
  const [providerError, setProviderError] = useState<string | null>(null)
  const [providerSaved, setProviderSaved] = useState(false)
  const [litertBusy, setLitertBusy] = useState<'start' | 'stop' | null>(null)

  async function load() {
    setState('loading')
    setError(null)
    try {
      const data = await fetchSettings()
      setSettings(data)
      setState('ready')
      // Sync form from the newly loaded config; tolerate legacy responses that
      // only had { mode, model }.
      const p = (data.provider as unknown as Record<string, unknown>) ?? {}
      const prov = (p['provider'] as ProviderType) ?? 'groq'
      setProvider(prov === 'local' ? 'local' : 'groq')
      setMode((p['mode'] as ProviderMode) ?? 'local_only')
      setGroqModel((p['groq_model'] as string) ?? (p['model'] as string) ?? '')
      setGroqBaseUrl((p['groq_base_url'] as string) ?? (p['base_url'] as string) ?? '')
      setLitertModel((p['litert_model'] as string) ?? '')
      setLitertBaseUrl((p['litert_base_url'] as string) ?? '')
      setProviderSaved(false)
      setProviderError(null)
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

  async function handleProviderSave() {
    setProviderSaving(true)
    setProviderError(null)
    setProviderSaved(false)
    try {
      const payload: Record<string, string> = { provider }
      // Only send mode when Groq is selected; local ignores it but we keep it persisted.
      if (provider === 'groq') payload['mode'] = mode
      else payload['mode'] = mode
      if (groqModel.trim()) payload['groq_model'] = groqModel.trim()
      if (groqBaseUrl.trim()) payload['groq_base_url'] = groqBaseUrl.trim()
      if (litertModel.trim()) payload['litert_model'] = litertModel.trim()
      if (litertBaseUrl.trim()) payload['litert_base_url'] = litertBaseUrl.trim()
      // Also set the effective model/base_url for the active provider so the
      // persisted row is self-consistent without a second read.
      if (provider === 'local') {
        if (litertModel.trim()) payload['model'] = litertModel.trim()
        if (litertBaseUrl.trim()) payload['base_url'] = litertBaseUrl.trim()
      } else {
        if (groqModel.trim()) payload['model'] = groqModel.trim()
        if (groqBaseUrl.trim()) payload['base_url'] = groqBaseUrl.trim()
      }
      await updateProvider(payload as never)
      await load()
      setProviderSaved(true)
    } catch (err) {
      setProviderError(err instanceof Error ? err.message : 'Could not save provider')
    } finally {
      setProviderSaving(false)
    }
  }

  async function handleLitert(action: 'start' | 'stop') {
    setLitertBusy(action)
    setProviderError(null)
    try {
      if (action === 'start') await startLocalLlm()
      else await stopLocalLlm()
      await load()
    } catch (err) {
      setProviderError(err instanceof Error ? err.message : `LiteRT ${action} failed`)
    } finally {
      setLitertBusy(null)
    }
  }

  if (state === 'loading') {
    return <p className="text-sm text-gray-400 py-4">Loading settings…</p>
  }

  if (state === 'error' || !settings) {
    return <p className="text-sm text-red-600 py-4">{error ?? 'Settings are unavailable.'}</p>
  }

  const litertStatus = settings.provider.litert_status
  const litertHealth = settings.provider.litert_health
  const activeProvider = (settings.provider.provider as ProviderType) ?? 'groq'

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
          <Row label="Provider">
            <span className="font-medium">{providerLabel(activeProvider)}</span>
          </Row>
          <Row label="Provider mode">
            <span className="font-medium">{modeLabel(settings.provider.mode)}</span>
          </Row>
          {settings.provider.model && <Row label="Model">{settings.provider.model}</Row>}
          {settings.provider.base_url && <Row label="Base URL">{settings.provider.base_url}</Row>}
          <Row label="Network egress">
            {settings.provider.egress_categories.length
              ? settings.provider.egress_categories.join('; ')
              : 'None — everything stays on this device'}
          </Row>
        </dl>
      </Section>

      <Section title="LLM Provider">
        <div className="space-y-4 text-sm text-gray-700">
          <p className="text-xs text-gray-500">
            Choose the execution target for question planning and narration. Local runs{' '}
            <span className="font-medium">gemma4-e2b</span> via LiteRT-LM on this device (no network
            egress). Groq is the hosted OpenAI-compatible provider. The choice is persisted and
            takes effect on the next chat without a restart.
          </p>

          <div className="space-y-2">
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
              Provider
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                aria-pressed={provider === 'local'}
                onClick={() => setProvider('local')}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${provider === 'local' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}`}
              >
                Local (LiteRT)
              </button>
              <button
                type="button"
                aria-pressed={provider === 'groq'}
                onClick={() => setProvider('groq')}
                className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${provider === 'groq' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}`}
              >
                Groq
              </button>
            </div>
          </div>

          {provider === 'groq' && (
            <div className="space-y-2">
              <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                Groq mode
              </label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as ProviderMode)}
                className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
              >
                <option value="local_only">Local only — no network egress</option>
                <option value="remote_planning">Remote question planning</option>
                <option value="remote_planning_and_narration">Remote planning + narration</option>
              </select>
              <p className="text-xs text-gray-400">{modeLabel(mode)}</p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                Groq model
              </label>
              <input
                value={groqModel}
                onChange={(e) => setGroqModel(e.target.value)}
                placeholder="llama-3.3-70b-versatile"
                className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
              />
              <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                Groq base URL
              </label>
              <input
                value={groqBaseUrl}
                onChange={(e) => setGroqBaseUrl(e.target.value)}
                placeholder="https://api.groq.com/openai/v1"
                className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                LiteRT model
              </label>
              <input
                value={litertModel}
                onChange={(e) => setLitertModel(e.target.value)}
                placeholder="gemma4-e2b"
                className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
              />
              <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
                LiteRT base URL
              </label>
              <input
                value={litertBaseUrl}
                onChange={(e) => setLitertBaseUrl(e.target.value)}
                placeholder="http://127.0.0.1:9379/v1"
                className="w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
              />
            </div>
          </div>

          {litertStatus && (
            <div className="rounded-md bg-gray-50 p-3 text-xs text-gray-600">
              <p className="font-medium text-gray-700">Local server</p>
              <p>
                Status:{' '}
                {litertStatus.running ? `running (pid ${litertStatus.pid ?? '—'})` : 'stopped'} ·{' '}
                {litertStatus.binary_available
                  ? `binary ${litertStatus.binary}`
                  : 'binary not found'}{' '}
                · model {litertStatus.model} · {litertStatus.base_url}
              </p>
              {litertHealth && (
                <p>
                  Health:{' '}
                  {litertHealth.ok
                    ? `ok (${litertHealth.latency_ms ?? '—'} ms)`
                    : `not ok${litertHealth.error ? ` — ${litertHealth.error}` : ''}`}
                </p>
              )}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleLitert('start')}
                  disabled={litertBusy !== null}
                  className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium hover:bg-gray-50 disabled:opacity-50"
                >
                  {litertBusy === 'start' ? 'Starting…' : 'Start local server'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleLitert('stop')}
                  disabled={litertBusy !== null}
                  className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium hover:bg-gray-50 disabled:opacity-50"
                >
                  {litertBusy === 'stop' ? 'Stopping…' : 'Stop local server'}
                </button>
              </div>
              {!litertStatus.binary_available && (
                <p className="mt-2 text-amber-600">
                  LiteRT binary not found. Install via{' '}
                  <code className="rounded bg-white px-1">pip install litert-lm</code> and import{' '}
                  <code className="rounded bg-white px-1">gemma4-e2b</code>, or set{' '}
                  <code className="rounded bg-white px-1">LITERT_SERVE_CMD</code>.
                </p>
              )}
            </div>
          )}

          {providerError && <p className="text-xs text-red-600">{providerError}</p>}
          {providerSaved && (
            <p className="text-xs text-green-600">
              Provider saved — next chat will use {providerLabel(provider)}.
            </p>
          )}
          <button
            type="button"
            onClick={() => void handleProviderSave()}
            disabled={providerSaving}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {providerSaving ? 'Saving…' : 'Save provider'}
          </button>
        </div>
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
