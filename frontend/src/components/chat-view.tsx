import { useState, useCallback, useEffect } from 'react'
import { askQuestion, ChatApiError } from '@/api/chat'
import type { ChatEnvelope } from '@/types/templates'
import { TemplateDispatch } from '@/components/template-dispatch'
import { ChatInput } from '@/components/chat-input'
import { SeedPrompts } from '@/components/seed-prompts'

type ChatState =
  | { status: 'idle' }
  | { status: 'loading'; question: string }
  | { status: 'success'; question: string; envelope: ChatEnvelope }
  | { status: 'error'; question: string; message: string }

/** Top-level chat page component: input → loading → template result. */
export function ChatView() {
  const [state, setState] = useState<ChatState>({ status: 'idle' })
  const [backendDown, setBackendDown] = useState(false)

  // Health check on mount (R1-12): non-blocking, 3s timeout
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 3000)
    fetch('/health', { signal: controller.signal })
      .then((r) => {
        if (!r.ok) setBackendDown(true)
      })
      .catch(() => setBackendDown(true))
      .finally(() => clearTimeout(timer))
  }, [])

  const handleQuestion = useCallback(async (question: string) => {
    setState({ status: 'loading', question })
    try {
      const envelope = await askQuestion(question)
      setState({ status: 'success', question, envelope })
    } catch (err) {
      const message =
        err instanceof ChatApiError
          ? `Request failed (${err.status}). Please try again.`
          : 'Something went wrong. Please try again.'
      setState({ status: 'error', question, message })
    }
  }, [])

  const isLoading = state.status === 'loading'

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">tti</h1>
        <p className="mt-1 text-gray-500">talk to your health data</p>
      </header>

      {backendDown ? (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Cannot connect to the backend. Make sure <code className="font-mono">make dev</code> is
          running on port 8000.
        </div>
      ) : null}

      <div className="space-y-4">
        <ChatInput onSubmit={handleQuestion} isLoading={isLoading} />
        <SeedPrompts onSelect={handleQuestion} disabled={isLoading} />
      </div>

      <div className="mt-8">
        {state.status === 'idle' && (
          <p className="text-center text-sm text-gray-400">
            Ask a question or pick one above to get started.
          </p>
        )}
        {state.status === 'loading' && (
          <div className="text-center">
            <p className="text-sm text-gray-500">
              Thinking about: <em>{state.question}</em>
            </p>
          </div>
        )}
        {state.status === 'error' && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <p className="text-sm font-medium text-red-700">Error</p>
            <p className="mt-1 text-sm text-red-600">{state.message}</p>
            <p className="mt-1 text-xs text-red-400">Question: {state.question}</p>
          </div>
        )}
        {state.status === 'success' && <TemplateDispatch envelope={state.envelope} />}
      </div>
    </div>
  )
}
