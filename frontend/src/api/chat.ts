import type { ChatEnvelope } from '@/types/templates'

export interface ChatRequest {
  question: string
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

export async function askQuestion(question: string): Promise<ChatEnvelope> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question } satisfies ChatRequest),
  })
  if (!response.ok) {
    throw new ChatApiError(response.status, `Chat request failed: ${response.status}`)
  }
  return response.json() as Promise<ChatEnvelope>
}
