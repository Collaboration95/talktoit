import { useState, useCallback, useEffect, useRef } from 'react'
import { askQuestion, ChatApiError } from '@/api/chat'
import {
  createConversation,
  archiveConversation,
  deleteConversation,
  getConversationTurns,
  listConversations,
  renameConversation,
  type Conversation,
} from '@/api/conversations'
import type { ChatEnvelope } from '@/types/templates'
import { TemplateDispatch } from '@/components/template-dispatch'
import { ChatInput } from '@/components/chat-input'
import { SeedPrompts } from '@/components/seed-prompts'

type ChatTurn =
  | { id: string; status: 'loading'; question: string }
  | { id: string; status: 'success'; question: string; envelope: ChatEnvelope; expanded: boolean }
  | { id: string; status: 'error'; question: string; message: string }

/** Top-level chat page component: input → loading → template result. */
export function ChatView() {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [conversationId, setConversationId] = useState<string>()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationSearch, setConversationSearch] = useState('')
  const [backendDown, setBackendDown] = useState(false)
  const activeRequest = useRef<AbortController | null>(null)
  const nextTurnId = useRef(0)
  const transcriptEnd = useRef<HTMLDivElement | null>(null)
  const readerIsAtBottom = useRef(true)

  const newTurnId = () => {
    nextTurnId.current += 1
    return `local-turn-${nextTurnId.current}`
  }

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

  useEffect(() => {
    const updateScrollAnchor = () => {
      const root = document.documentElement
      readerIsAtBottom.current = window.innerHeight + window.scrollY >= root.scrollHeight - 96
    }
    updateScrollAnchor()
    window.addEventListener('scroll', updateScrollAnchor, { passive: true })
    return () => window.removeEventListener('scroll', updateScrollAnchor)
  }, [])

  useEffect(() => {
    if (!readerIsAtBottom.current) return
    transcriptEnd.current?.scrollIntoView?.({ block: 'end' })
  }, [turns])

  const handleQuestion = useCallback(
    async (question: string) => {
      const activeConversation = conversationId ?? (await createConversation(question.slice(0, 80)))
      if (!conversationId) {
        setConversationId(activeConversation)
        setConversations(await listConversations())
      }
      const turnId = newTurnId()
      setTurns((current) => [...current, { id: turnId, status: 'loading', question }])
      const controller = new AbortController()
      activeRequest.current = controller
      try {
        const signal = navigator.userAgent.includes('jsdom') ? undefined : controller.signal
        const envelope = await askQuestion(question, {
          conversationId: activeConversation,
          ...(signal ? { signal } : {}),
        })
        if (activeRequest.current !== controller) return
        setTurns((current) => [
          ...current.slice(0, -1),
          { id: turnId, status: 'success', question, envelope, expanded: true },
        ])
      } catch (err) {
        if (activeRequest.current !== controller) return
        const message = controller.signal.aborted
          ? 'This request was cancelled.'
          : err instanceof ChatApiError
            ? `Request failed (${err.status}). Please try again.`
            : 'Something went wrong. Please try again.'
        setTurns((current) => [
          ...current.slice(0, -1),
          { id: turnId, status: 'error', question, message },
        ])
      } finally {
        if (activeRequest.current === controller) activeRequest.current = null
      }
    },
    [conversationId],
  )

  const cancelActiveRequest = useCallback(() => {
    if (!activeRequest.current) return
    activeRequest.current.abort()
    activeRequest.current = null
    setTurns((current) => {
      const last = current.at(-1)
      if (!last || last.status !== 'loading') return current
      return [
        ...current.slice(0, -1),
        {
          id: last.id,
          status: 'error',
          question: last.question,
          message: 'This request was cancelled.',
        },
      ]
    })
  }, [])

  const isLoading = turns.some((turn) => turn.status === 'loading')

  const selectConversation = useCallback(async (id: string) => {
    const stored = await getConversationTurns(id)
    setConversationId(id)
    setTurns(
      stored.map((turn, index) => {
        const id = turn.id
        if (turn.state === 'completed' && turn.response_json) {
          return {
            id,
            status: 'success' as const,
            question: turn.question,
            envelope: JSON.parse(turn.response_json) as ChatEnvelope,
            expanded: index === stored.length - 1,
          }
        }
        return {
          id,
          status: 'error' as const,
          question: turn.question,
          message:
            turn.error_message ??
            (turn.state === 'cancelled'
              ? 'This request was cancelled.'
              : 'This request could not be completed.'),
        }
      }),
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

  const renameConversationFromWorkspace = useCallback(
    async (conversation: Conversation) => {
      const title = window.prompt('Rename this local conversation', conversation.title)?.trim()
      if (!title || title === conversation.title) return
      await renameConversation(conversation.id, title)
      setConversations(await listConversations(conversationSearch))
    },
    [conversationSearch],
  )

  const copyAnswer = useCallback((narrative: string) => {
    void navigator.clipboard?.writeText(narrative)
  }, [])

  const toggleTurnDetails = useCallback((turnId: string) => {
    setTurns((current) =>
      current.map((turn) =>
        turn.id === turnId && turn.status === 'success'
          ? { ...turn, expanded: !turn.expanded }
          : turn,
      ),
    )
  }, [])

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
                  onClick={() => void renameConversationFromWorkspace(conversation)}
                  className="ml-1 text-xs text-gray-600"
                  aria-label={`Rename ${conversation.title}`}
                >
                  Rename
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
        <ChatInput onSubmit={handleQuestion} onCancel={cancelActiveRequest} isLoading={isLoading} />
        <SeedPrompts onSelect={handleQuestion} disabled={isLoading} />
      </div>

      <div className="mt-8">
        {turns.length === 0 && (
          <p className="text-center text-sm text-gray-400">
            Ask a question or pick one above to get started.
          </p>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className="space-y-4">
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Query</p>
              <p className="mt-0.5 text-sm text-gray-700">{turn.question}</p>
            </div>
            {turn.status === 'loading' ? (
              <p className="text-sm text-gray-500">Thinking about: {turn.question}</p>
            ) : null}
            {turn.status === 'success' ? (
              <button
                type="button"
                className="text-sm text-blue-600"
                onClick={() => toggleTurnDetails(turn.id)}
                aria-expanded={turn.expanded}
              >
                {turn.expanded ? 'Hide answer details' : 'Show answer details'}
              </button>
            ) : null}
            {turn.status === 'success' && turn.expanded ? (
              <TemplateDispatch envelope={turn.envelope} />
            ) : null}
            {turn.status === 'success' && turn.expanded ? (
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <p>
                  {turn.envelope.metadata?.provenance === 'cached'
                    ? 'Cached local answer'
                    : turn.envelope.metadata?.provenance === 'deterministic_local'
                      ? 'Deterministic local answer'
                      : 'Generated answer'}
                  {turn.envelope.metadata?.coverage_start && turn.envelope.metadata?.coverage_end
                    ? ` · data coverage ${turn.envelope.metadata.coverage_start} to ${turn.envelope.metadata.coverage_end}`
                    : ''}
                  {turn.envelope.metadata?.dataset_version_id
                    ? ` · dataset ${turn.envelope.metadata.dataset_version_id}`
                    : ''}
                </p>
                <button
                  type="button"
                  className="text-blue-600"
                  onClick={() => copyAnswer(turn.envelope.narrative)}
                >
                  Copy answer
                </button>
              </div>
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
        <div ref={transcriptEnd} aria-hidden="true" />
      </div>
    </div>
  )
}
