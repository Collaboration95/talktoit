export type ImportState = 'queued' | 'running' | 'succeeded' | 'failed'

export interface ImportJob {
  id: string
  filename: string
  state: ImportState
  progress: number
  report: {
    mode?: string
    source_size_bytes?: number
    resolved_workers?: number
    dataset_version_id?: string
    coverage_start?: string | null
    coverage_end?: string | null
    counts?: Record<string, number>
    timing_seconds?: Record<string, number>
    warnings?: string[]
  } | null
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

async function checkedFetch(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Import request failed: ${response.status}`)
  }
  return response
}

export async function startImport(file: File): Promise<ImportJob> {
  const filename = encodeURIComponent(file.name || 'export.xml')
  // Modern browsers can stream a File directly; the ArrayBuffer fallback
  // keeps the same API testable in jsdom, whose File lacks stream().
  const body = typeof file.stream === 'function' ? file.stream() : await file.arrayBuffer()
  const response = await checkedFetch(`/api/imports?filename=${filename}`, {
    method: 'POST',
    headers: { 'Content-Type': file.type || 'application/xml' },
    body,
  })
  return response.json() as Promise<ImportJob>
}

export async function fetchImport(jobId: string): Promise<ImportJob> {
  const response = await checkedFetch(`/api/imports/${encodeURIComponent(jobId)}`)
  return response.json() as Promise<ImportJob>
}
