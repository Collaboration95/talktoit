export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface StoredTurn {
  question: string
  state: 'completed' | 'failed' | 'cancelled'
  response_json: string | null
  error_message: string | null
}

export async function createConversation(title = 'New conversation'): Promise<string> {
  const response = await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) throw new Error('Could not create conversation')
  return ((await response.json()) as { id: string }).id
}

export async function listConversations(search = ''): Promise<Conversation[]> {
  const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : ''
  const response = await fetch(`/api/conversations${query}`)
  if (!response.ok) throw new Error('Could not load conversations')
  return response.json() as Promise<Conversation[]>
}

export async function getConversationTurns(id: string): Promise<StoredTurn[]> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(id)}/turns`)
  if (!response.ok) throw new Error('Could not load conversation')
  return response.json() as Promise<StoredTurn[]>
}

export async function renameConversation(id: string, title: string): Promise<void> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!response.ok) throw new Error('Could not rename conversation')
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Could not delete conversation')
}

export async function archiveConversation(id: string): Promise<void> {
  const response = await fetch(`/api/conversations/${encodeURIComponent(id)}/archive`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Could not archive conversation')
}
