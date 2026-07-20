import { useState, useCallback, useEffect } from 'react'
import { askQuestion, ChatApiError } from '@/api/chat'
import {
  createConversation,
  archiveConversation,
  deleteConversation,
  getConversationTurns,
  listConversations,
  type Conversation,
} from '@/api/conversations'
import type { ChatEnvelope } from '@/types/templates'
import { TemplateDispatch } from '@/components/template-dispatch'
import { ChatInput } from '@/components/chat-input'
import { SeedPrompts } from '@/components/seed-prompts'

type ChatTurn =
  | { status: 'loading'; question: string }
  | { status: 'success'; question: string; envelope: ChatEnvelope }
  | { status: 'error'; question: string; message: string }

/** Top-level chat page component: input → loading → template result. */
export function ChatView() {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [conversationId, setConversationId] = useState<string>()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationSearch, setConversationSearch] = useState('')
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

  useEffect(() => {
    listConversations(conversationSearch)
      .then(setConversations)
      .catch(() => undefined)
  }, [conversationId, conversationSearch])

  const handleQuestion = useCallback(
    async (question: string) => {
      const activeConversation = conversationId ?? (await createConversation(question.slice(0, 80)))
      if (!conversationId) {
        setConversationId(activeConversation)
        setConversations(await listConversations())
      }
      setTurns((current) => [...current, { status: 'loading', question }])
      try {
        const envelope = await askQuestion(question, { conversationId: activeConversation })
        setTurns((current) => [...current.slice(0, -1), { status: 'success', question, envelope }])
      } catch (err) {
        const message =
          err instanceof ChatApiError
            ? `Request failed (${err.status}). Please try again.`
            : 'Something went wrong. Please try again.'
        setTurns((current) => [...current.slice(0, -1), { status: 'error', question, message }])
      }
    },
    [conversationId],
  )

  const isLoading = turns.some((turn) => turn.status === 'loading')

  const selectConversation = useCallback(async (id: string) => {
    const stored = await getConversationTurns(id)
    setConversationId(id)
    setTurns(
      stored.map((turn) => ({
        status: 'success' as const,
        question: turn.question,
        envelope: JSON.parse(turn.response_json) as ChatEnvelope,
      })),
    )
  }, [])

  const removeConversation = useCallback(
    async (id: string) => {
      if (!window.confirm('Delete this local conversation? Health data will not be affected.'))
        return
      await deleteConversation(id)
      if (conversationId === id) {
        setConversationId(undefined)
        setTurns([])
      }
      setConversations(await listConversations())
    },
    [conversationId],
  )

  const archiveConversationFromWorkspace = useCallback(
    async (id: string) => {
      await archiveConversation(id)
      if (conversationId === id) {
        setConversationId(undefined)
        setTurns([])
      }
      setConversations(await listConversations())
    },
    [conversationId],
  )

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
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500">{conversations.length} local conversations</span>
          <button
            onClick={() => {
              setConversationId(undefined)
              setTurns([])
            }}
            className="text-blue-600"
          >
            New conversation
          </button>
        </div>
        <input
          type="search"
          value={conversationSearch}
          onChange={(event) => setConversationSearch(event.target.value)}
          aria-label="Search local conversations"
          placeholder="Search local conversations"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
        />
        {conversations.length > 0 ? (
          <ul className="flex flex-wrap gap-2" aria-label="Local conversations">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  onClick={() => void selectConversation(conversation.id)}
                  className="text-sm text-blue-600"
                >
                  {conversation.title}
                </button>
                <button
                  onClick={() => void archiveConversationFromWorkspace(conversation.id)}
                  className="ml-1 text-xs text-gray-600"
                  aria-label={`Archive ${conversation.title}`}
                >
                  Archive
                </button>
                <button
                  onClick={() => void removeConversation(conversation.id)}
                  className="ml-1 text-xs text-red-600"
                  aria-label={`Delete ${conversation.title}`}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <ChatInput onSubmit={handleQuestion} isLoading={isLoading} />
        <SeedPrompts onSelect={handleQuestion} disabled={isLoading} />
      </div>

      <div className="mt-8">
        {turns.length === 0 && (
          <p className="text-center text-sm text-gray-400">
            Ask a question or pick one above to get started.
          </p>
        )}
        {turns.map((turn) => (
          <div key={turn.question} className="space-y-4">
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Query</p>
              <p className="mt-0.5 text-sm text-gray-700">{turn.question}</p>
            </div>
            {turn.status === 'loading' ? (
              <p className="text-sm text-gray-500">Thinking about: {turn.question}</p>
            ) : null}
            {turn.status === 'success' ? <TemplateDispatch envelope={turn.envelope} /> : null}
            {turn.status === 'success' ? (
              <p className="text-xs text-gray-500">
                {turn.envelope.metadata?.provenance === 'cached'
                  ? 'Cached local answer'
                  : turn.envelope.metadata?.provenance === 'deterministic_local'
                    ? 'Deterministic local answer'
                    : 'Generated answer'}
              </p>
            ) : null}
            {turn.status === 'error' ? (
              <div className="flex items-center gap-3">
                <p className="text-sm text-red-600">{turn.message}</p>
                <button
                  type="button"
                  className="text-sm text-blue-600"
                  onClick={() => void handleQuestion(turn.question)}
                >
                  Retry
                </button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}
