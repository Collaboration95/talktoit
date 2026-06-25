import { type FormEvent, useRef } from 'react'

interface ChatInputProps {
  onSubmit: (question: string) => void
  isLoading: boolean
}

/**
 * Question input box with submit button.
 * Submits on Enter (without Shift) or button click.
 */
export function ChatInput({ onSubmit, isLoading }: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const value = inputRef.current?.value.trim()
    if (!value || isLoading) return
    onSubmit(value)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <textarea
        ref={inputRef}
        rows={2}
        aria-label="Ask a question about your health data"
        placeholder="Ask about your health data…"
        disabled={isLoading}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSubmit(e)
          }
        }}
        className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
      />
      <button
        type="submit"
        disabled={isLoading}
        className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLoading ? 'Thinking…' : 'Ask'}
      </button>
    </form>
  )
}
