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
  type StoredTurn,
} from '@/api/conversations'
import type { ChatEnvelope } from '@/types/templates'
import { TemplateDispatch } from '@/components/template-dispatch'
import { ChatInput } from '@/components/chat-input'
import { SeedPrompts } from '@/components/seed-prompts'
import { useBackendHealth } from '@/lib/use-backend-health'

type ChatTurn =
  | { id: string; status: 'loading'; question: string }
  | { id: string; status: 'success'; question: string; envelope: ChatEnvelope; expanded: boolean }
  | { id: string; status: 'error'; question: string; message: string }

/** Notice shown above degraded fallback answers (GH-47).

The fallback envelope means the full answer was unavailable — most often
because the local language model is stopped. The copy stays factual and
names the remedy without leaking prompts, SQL, or internals. */
function FallbackNotice() {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
      <p>
        Showing a basic summary of your data. If the local language model is stopped, start it in
        Settings for richer answers.
      </p>
      <button
        type="button"
        className="mt-1 text-xs text-amber-700 underline"
        onClick={() => setDismissed(true)}
      >
        Dismiss
      </button>
    </div>
  )
}

/** Return a safe, human-readable message for a failed local request. */
function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

/** Top-level chat page component: input → loading → template result. */
export function ChatView() {
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [conversationId, setConversationId] = useState<string>()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationSearch, setConversationSearch] = useState('')
  const [conversationError, setConversationError] = useState<string | null>(null)
  const backendDown = useBackendHealth()
  const inFlight = useRef(new Map<string, AbortController>())
  const conversationRef = useRef<string | undefined>(undefined)
  const conversationCreation = useRef<Promise<string> | null>(null)
  const selectionGeneration = useRef(0)
  const nextTurnId = useRef(0)
  const transcriptEnd = useRef<HTMLDivElement | null>(null)
  const readerIsAtBottom = useRef(true)

  const newTurnId = () => {
    nextTurnId.current += 1
    return `local-turn-${nextTurnId.current}`
  }

  // Health check on mount is shared with the dashboard view via
  // useBackendHealth (R1-12).

  /** Invalidate any pending conversation load so a late response cannot land. */
  const invalidatePendingLoads = useCallback(() => {
    selectionGeneration.current += 1
    return selectionGeneration.current
  }, [])

  /** Abort live turns and reset to the idle transcript of a new conversation. */
  const resetTranscript = useCallback(() => {
    invalidatePendingLoads()
    conversationRef.current = undefined
    conversationCreation.current = null
    for (const controller of inFlight.current.values()) controller.abort()
    inFlight.current.clear()
    setConversationId(undefined)
    setTurns([])
  }, [invalidatePendingLoads])

  /** Refresh the sidebar list, surfacing a failure instead of dropping it. */
  const refreshConversationList = useCallback(async () => {
    try {
      setConversations(await listConversations(conversationSearch))
      setConversationError(null)
    } catch (err) {
      setConversationError(messageOf(err, 'Could not load conversations.'))
    }
  }, [conversationSearch])

  useEffect(() => {
    let active = true
    listConversations(conversationSearch)
      .then((items) => {
        if (!active) return
        setConversations(items)
        setConversationError(null)
      })
      .catch((err: unknown) => {
        if (active) setConversationError(messageOf(err, 'Could not load conversations.'))
      })
    return () => {
      active = false
    }
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
      const turnId = newTurnId()
      setTurns((current) => [...current, { id: turnId, status: 'loading', question }])
      const controller = new AbortController()
      inFlight.current.set(turnId, controller)
      try {
        let activeConversation = conversationRef.current ?? conversationId
        if (!activeConversation) {
          // Resolve the conversation inside the handled block so a create
          // failure becomes a visible turn error instead of a stray rejection.
          if (conversationCreation.current === null) {
            conversationCreation.current = createConversation(question.slice(0, 80))
          }
          const creation = conversationCreation.current
          try {
            activeConversation = await creation
          } finally {
            if (conversationCreation.current === creation) conversationCreation.current = null
          }
          conversationRef.current = activeConversation
          setConversationId(activeConversation)
          await refreshConversationList()
        }
        const envelope = await askQuestion(question, {
          conversationId: activeConversation,
          signal: controller.signal,
        })
        setTurns((current) =>
          current.map((turn) =>
            turn.id === turnId
              ? { id: turnId, status: 'success' as const, question, envelope, expanded: true }
              : turn,
          ),
        )
      } catch (err) {
        const message = controller.signal.aborted
          ? 'This request was cancelled.'
          : err instanceof ChatApiError
            ? messageOf(err, 'The answer could not be completed. Please try again.')
            : messageOf(err, 'Something went wrong. Please try again.')
        setTurns((current) =>
          current.map((turn) =>
            turn.id === turnId ? { id: turnId, status: 'error' as const, question, message } : turn,
          ),
        )
      } finally {
        inFlight.current.delete(turnId)
      }
    },
    [conversationId, refreshConversationList],
  )

  const cancelActiveRequest = useCallback(() => {
    for (const controller of inFlight.current.values()) controller.abort()
    inFlight.current.clear()
    setTurns((current) =>
      current.map((turn) =>
        turn.status === 'loading'
          ? {
              id: turn.id,
              status: 'error' as const,
              question: turn.question,
              message: 'This request was cancelled.',
            }
          : turn,
      ),
    )
  }, [])

  const isLoading = turns.some((turn) => turn.status === 'loading')

  const selectConversation = useCallback(
    async (id: string) => {
      const generation = invalidatePendingLoads()
      for (const controller of inFlight.current.values()) controller.abort()
      inFlight.current.clear()
      conversationCreation.current = null
      let stored: StoredTurn[]
      try {
        stored = await getConversationTurns(id)
      } catch (err) {
        if (generation === selectionGeneration.current) {
          setConversationError(messageOf(err, 'Could not load that conversation.'))
        }
        return
      }
      if (generation !== selectionGeneration.current) return
      conversationRef.current = id
      setConversationId(id)
      setTurns(
        stored.map((turn, index) => {
          const turnId = turn.id
          if (turn.state === 'completed' && turn.response_json) {
            return {
              id: turnId,
              status: 'success' as const,
              question: turn.question,
              envelope: JSON.parse(turn.response_json) as ChatEnvelope,
              expanded: index === stored.length - 1,
            }
          }
          return {
            id: turnId,
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
    },
    [invalidatePendingLoads],
  )

  const removeConversation = useCallback(
    async (id: string) => {
      if (!window.confirm('Delete this local conversation? Health data will not be affected.'))
        return
      const wasActive = conversationId === id || conversationRef.current === id
      invalidatePendingLoads()
      try {
        await deleteConversation(id)
      } catch (err) {
        setConversationError(messageOf(err, 'Could not delete this conversation.'))
        return
      }
      if (wasActive) resetTranscript()
      await refreshConversationList()
    },
    [conversationId, invalidatePendingLoads, refreshConversationList, resetTranscript],
  )

  const archiveConversationFromWorkspace = useCallback(
    async (id: string) => {
      const wasActive = conversationId === id || conversationRef.current === id
      invalidatePendingLoads()
      try {
        await archiveConversation(id)
      } catch (err) {
        setConversationError(messageOf(err, 'Could not archive this conversation.'))
        return
      }
      if (wasActive) resetTranscript()
      await refreshConversationList()
    },
    [conversationId, invalidatePendingLoads, refreshConversationList, resetTranscript],
  )

  const renameConversationFromWorkspace = useCallback(
    async (conversation: Conversation) => {
      const title = window.prompt('Rename this local conversation', conversation.title)?.trim()
      if (!title || title === conversation.title) return
      try {
        await renameConversation(conversation.id, title)
      } catch (err) {
        setConversationError(messageOf(err, 'Could not rename this conversation.'))
        return
      }
      await refreshConversationList()
    },
    [refreshConversationList],
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
          <button onClick={() => resetTranscript()} className="text-blue-600">
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
        {conversationError ? <p className="text-xs text-red-600">{conversationError}</p> : null}
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
        {turns.length === 0 ? (
          <>
            <ChatInput
              onSubmit={handleQuestion}
              onCancel={cancelActiveRequest}
              isLoading={isLoading}
            />
            <SeedPrompts onSelect={handleQuestion} disabled={isLoading} />
          </>
        ) : null}
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
            {turn.status === 'success' && turn.envelope.template_id === 'fallback' ? (
              <FallbackNotice />
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

      {turns.length > 0 ? (
        <div
          data-testid="composer-bar"
          className="sticky bottom-0 -mx-4 mt-8 border-t border-gray-200 bg-gray-50/95 px-4 pb-4 pt-3 backdrop-blur"
        >
          <ChatInput
            onSubmit={handleQuestion}
            onCancel={cancelActiveRequest}
            isLoading={isLoading}
          />
        </div>
      ) : null}
    </div>
  )
}
