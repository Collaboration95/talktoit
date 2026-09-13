import type { DashboardQuery } from '@/lib/dashboard-query'
import { checkedFetch } from '@/api/checked-fetch'

export interface SavedView {
  id: string
  title: string
  query: DashboardQuery
}

export async function listSavedViews(): Promise<SavedView[]> {
  const response = await checkedFetch('/api/saved-views', undefined, 'Saved view request failed')
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
