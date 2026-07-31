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
    public readonly code?: string,
    public readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ChatApiError'
  }
}

export async function askQuestion(
  question: string,
  options: {
    conversationId?: string
    cacheMode?: 'default' | 'fresh'
    signal?: AbortSignal
  } = {},
): Promise<ChatEnvelope> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      ...(options.conversationId ? { conversation_id: options.conversationId } : {}),
      ...(options.cacheMode ? { cache_mode: options.cacheMode } : {}),
    } satisfies ChatRequest),
    ...(options.signal ? { signal: options.signal } : {}),
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: { code?: string; message?: string; request_id?: string } | string
    } | null
    const detail = payload?.detail
    if (typeof detail === 'object' && detail !== null) {
      throw new ChatApiError(
        response.status,
        detail.message ?? `Chat request failed: ${response.status}`,
        detail.code,
        detail.request_id,
      )
    }
    throw new ChatApiError(
      response.status,
      typeof detail === 'string' ? detail : `Chat request failed: ${response.status}`,
    )
  }
  return response.json() as Promise<ChatEnvelope>
}
