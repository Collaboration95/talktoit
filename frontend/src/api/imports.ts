import { checkedFetch } from '@/api/checked-fetch'

export type ImportState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface ImportJob {
  id: string
  filename: string
  state: ImportState
  progress: number
  cancelled?: boolean
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

export async function startImport(file: File, signal?: AbortSignal): Promise<ImportJob> {
  const filename = encodeURIComponent(file.name || 'export.xml')
  // Fetch streams native File bodies without the duplex/HTTP2 requirements
  // of a naked ReadableStream. jsdom needs the ArrayBuffer fallback.
  const body = typeof file.stream === 'function' ? file : await file.arrayBuffer()
  const response = await checkedFetch(`/api/imports?filename=${filename}`, {
    method: 'POST',
    ...(signal ? { signal } : {}),
    headers: { 'Content-Type': file.type || 'application/xml' },
    body,
  })
  return response.json() as Promise<ImportJob>
}

export async function fetchImport(jobId: string, signal?: AbortSignal): Promise<ImportJob> {
  const response = await checkedFetch(
    `/api/imports/${encodeURIComponent(jobId)}`,
    signal ? { signal } : undefined,
  )
  return response.json() as Promise<ImportJob>
}

/** Return process-local jobs so Settings can reconnect after navigation. */
export async function listImports(signal?: AbortSignal): Promise<ImportJob[]> {
  const response = await checkedFetch('/api/imports', signal ? { signal } : undefined)
  return response.json() as Promise<ImportJob[]>
}

/** Ask the backend to cancel; callers reconcile already-finished races by reading the job. */
export async function cancelImport(jobId: string, signal?: AbortSignal): Promise<ImportJob> {
  const response = await checkedFetch(`/api/imports/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
    ...(signal ? { signal } : {}),
  })
  return response.json() as Promise<ImportJob>
}
