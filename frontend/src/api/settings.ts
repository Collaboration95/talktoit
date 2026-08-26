// Settings and data-lifecycle introspection client. Settings are read-only
// service state; destructive operations are explicitly scoped and require a
// confirmation payload.

export type ProviderMode = 'local_only' | 'remote_planning' | 'remote_planning_and_narration'
export type ProviderType = 'local' | 'groq'

export interface LitertStatus {
  running: boolean
  pid: number | null
  base_url: string
  model: string
  binary: string | null
  binary_available: boolean
  pidfile: string
  log_path: string
}

export interface LitertHealth {
  ok: boolean
  latency_ms?: number
  status_code?: number
  error?: string
}

export interface DatasetVersion {
  id: string
  content_hash_prefix: string
  source_size_bytes: number
  parser_version: string
  schema_version: string
  worker_count: number
  coverage_start: string | null
  coverage_end: string | null
  counts: Record<string, number>
  warnings: string[]
  imported_at: string
  activated_at: string | null
  status: string
}

export interface ProviderConfig {
  provider: ProviderType
  mode: ProviderMode
  model: string | null
  base_url: string | null
  groq_model: string | null
  groq_base_url: string | null
  litert_model: string | null
  litert_base_url: string | null
  egress_categories: string[]
  litert_status?: LitertStatus
  litert_health?: LitertHealth | null
}

export interface Settings {
  dataset: DatasetVersion | null
  provider: ProviderConfig
  storage: {
    app_state_bytes: number
    health_db_bytes: number
    cache: { entries: number; bytes: number }
    conversations: number
    saved_views: number
    diagnostics_events: number
  }
  quality: {
    active: boolean
    parser_version: string | null
    schema_version: string | null
    coverage_start: string | null
    coverage_end: string | null
    warnings: string[]
    metric_states: Record<string, string>
    vocabulary: string[]
  }
}

export type ClearScope = 'cache' | 'history' | 'diagnostics' | 'health'

export type DestroyResult = { cleared?: number; deleted?: number; scope: ClearScope }

async function checkedFetch(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init)
  if (!response.ok) throw new Error(`Settings request failed: ${response.status}`)
  return response
}

export async function fetchSettings(): Promise<Settings> {
  const response = await checkedFetch('/api/settings')
  return response.json() as Promise<Settings>
}

export async function clearScope(scope: ClearScope): Promise<DestroyResult> {
  const response = await checkedFetch(`/api/settings/${scope}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: true, scope }),
  })
  return response.json() as Promise<DestroyResult>
}

export interface ProviderUpdate {
  provider: ProviderType
  mode?: ProviderMode
  model?: string | null
  base_url?: string | null
  groq_model?: string | null
  groq_base_url?: string | null
  litert_model?: string | null
  litert_base_url?: string | null
}

export async function updateProvider(payload: ProviderUpdate): Promise<ProviderConfig> {
  const response = await checkedFetch('/api/settings/provider', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return response.json() as Promise<ProviderConfig>
}

export interface LlmHealth {
  provider: ProviderType
  model?: string | null
  base_url?: string | null
  mode?: ProviderMode
  status?: LitertStatus
  health?: LitertHealth
  ok?: boolean
  error?: string
  egress_categories?: string[]
}

export async function fetchLlmHealth(): Promise<LlmHealth> {
  const response = await checkedFetch('/api/settings/llm/health')
  return response.json() as Promise<LlmHealth>
}

export async function startLocalLlm(): Promise<Record<string, unknown>> {
  const response = await checkedFetch('/api/settings/llm/start', { method: 'POST' })
  return response.json() as Promise<Record<string, unknown>>
}

export async function stopLocalLlm(): Promise<Record<string, unknown>> {
  const response = await checkedFetch('/api/settings/llm/stop', { method: 'POST' })
  return response.json() as Promise<Record<string, unknown>>
}
