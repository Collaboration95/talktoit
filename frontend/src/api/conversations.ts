export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
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

export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch('/api/conversations')
  if (!response.ok) throw new Error('Could not load conversations')
  return response.json() as Promise<Conversation[]>
}
