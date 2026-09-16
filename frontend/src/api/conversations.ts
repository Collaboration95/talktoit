import { checkedFetch } from '@/api/checked-fetch'

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface StoredTurn {
  id: string
  question: string
  state: 'completed' | 'failed' | 'cancelled'
  response_json: string | null
  error_message: string | null
}

export async function createConversation(title = 'New conversation'): Promise<string> {
  const response = await checkedFetch('/api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return ((await response.json()) as { id: string }).id
}

export async function listConversations(search = ''): Promise<Conversation[]> {
  const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : ''
  const response = await checkedFetch(
    `/api/conversations${query}`,
    undefined,
    'Could not load conversations',
  )
  return response.json() as Promise<Conversation[]>
}

export async function getConversationTurns(id: string): Promise<StoredTurn[]> {
  const response = await checkedFetch(`/api/conversations/${encodeURIComponent(id)}/turns`)
  return response.json() as Promise<StoredTurn[]>
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await checkedFetch(`/api/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export async function deleteConversation(id: string): Promise<void> {
  await checkedFetch(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function archiveConversation(id: string): Promise<void> {
  await checkedFetch(`/api/conversations/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
  })
}
