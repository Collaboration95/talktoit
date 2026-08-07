// Privacy-safe local diagnostics client. Responses contain aggregates and
// event metadata only — never question text, health values, routes, or paths.

export type DiagnosticsCategory =
  | 'import'
  | 'query'
  | 'chat'
  | 'planner'
  | 'narrator'
  | 'panel'
  | 'app'
  | 'benchmark'

export interface DiagnosticsCategoryStats {
  count: number
  mean_duration_ms: number | null
  p95_duration_ms: number | null
}

export interface DiagnosticsSummary {
  total_events: number
  by_category: Record<DiagnosticsCategory, DiagnosticsCategoryStats>
  status_counts: Record<string, number>
  cache: { hits: number; misses: number; hit_rate: number | null }
  cache_outcomes: Record<string, number>
}

export interface DiagnosticsEvent {
  id: string
  category: DiagnosticsCategory | string
  name: string
  status: string
  duration_ms: number | null
  counts: Record<string, number>
  meta: Record<string, string>
  created_at: string
}

export interface DiagnosticsEventsResponse {
  count: number
  events: DiagnosticsEvent[]
}

async function checkedFetch(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init)
  if (!response.ok) throw new Error(`Diagnostics request failed: ${response.status}`)
  return response
}

export async function fetchDiagnosticsSummary(): Promise<DiagnosticsSummary> {
  const response = await checkedFetch('/api/diagnostics')
  return response.json() as Promise<DiagnosticsSummary>
}

export async function fetchDiagnosticsEvents(
  category?: DiagnosticsCategory,
  limit = 50,
): Promise<DiagnosticsEventsResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (category) params.set('category', category)
  const response = await checkedFetch(`/api/diagnostics/events?${params.toString()}`)
  return response.json() as Promise<DiagnosticsEventsResponse>
}

export async function clearDiagnostics(): Promise<number> {
  const response = await checkedFetch('/api/diagnostics', { method: 'DELETE' })
  return ((await response.json()) as { cleared: number }).cleared
}

export async function exportDiagnostics(): Promise<{
  redacted: boolean
  export: DiagnosticsSummary
}> {
  const response = await checkedFetch('/api/diagnostics/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed: true }),
  })
  return response.json() as Promise<{ redacted: boolean; export: DiagnosticsSummary }>
}
