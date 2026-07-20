import type { ChatEnvelope } from '@/types/templates'

export interface ChatRequest {
  question: string
  request_id?: string
  conversation_id?: string
  parent_turn_id?: string
  cache_mode?: 'default' | 'fresh'
}

export class ChatApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ChatApiError'
  }
}

export async function askQuestion(
  question: string,
  options: { conversationId?: string; cacheMode?: 'default' | 'fresh' } = {},
): Promise<ChatEnvelope> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      ...(options.conversationId ? { conversation_id: options.conversationId } : {}),
      ...(options.cacheMode ? { cache_mode: options.cacheMode } : {}),
    } satisfies ChatRequest),
  })
  if (!response.ok) {
    throw new ChatApiError(response.status, `Chat request failed: ${response.status}`)
  }
  return response.json() as Promise<ChatEnvelope>
}
