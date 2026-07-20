import type { DashboardQuery } from '@/lib/dashboard-query'

export interface SavedView {
  id: string
  title: string
  query: DashboardQuery
}

async function checkedFetch(url: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(url, init)
  if (!response.ok) throw new Error(`Saved view request failed: ${response.status}`)
  return response
}

export async function listSavedViews(): Promise<SavedView[]> {
  const response = await checkedFetch('/api/saved-views')
  return response.json() as Promise<SavedView[]>
}

export async function createSavedView(title: string, query: DashboardQuery): Promise<string> {
  const response = await checkedFetch('/api/saved-views', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, query }),
  })
  return ((await response.json()) as { id: string }).id
}
