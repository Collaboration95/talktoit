import { useState } from 'react'
import { ChatView } from '@/components/chat-view'
import { DashboardView } from '@/components/dashboard-view'
import { DiagnosticsView } from '@/components/diagnostics-view'

/** Resolve the top-level view from the URL on first load (backwards compatible). */
function initialTab(): 'chat' | 'dashboard' | 'diagnostics' {
  const tab = new URLSearchParams(window.location.search).get('tab')
  if (tab === 'workouts' || tab === 'dashboard') return 'dashboard'
  if (tab === 'diagnostics') return 'diagnostics'
  return 'chat'
}

/** Keep the URL tab in sync with the visible view without dropping dashboard state. */
function pushTab(tab: 'chat' | 'dashboard' | 'diagnostics') {
  const params = new URLSearchParams(window.location.search)
  params.set('tab', tab)
  window.history.pushState({}, '', `?${params.toString()}`)
}

export function App() {
  const [tab, setTab] = useState<'chat' | 'dashboard' | 'diagnostics'>(initialTab)

  const selectTab = (next: 'chat' | 'dashboard' | 'diagnostics') => {
    setTab(next)
    pushTab(next)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-3xl gap-4 px-4 py-3">
          <button
            onClick={() => selectTab('chat')}
            className={`text-sm font-medium ${tab === 'chat' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Chat
          </button>
          <button
            onClick={() => selectTab('dashboard')}
            className={`text-sm font-medium ${tab === 'dashboard' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Dashboard
          </button>
          <button
            onClick={() => selectTab('diagnostics')}
            className={`text-sm font-medium ${tab === 'diagnostics' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Diagnostics
          </button>
        </div>
      </nav>
      {tab === 'chat' ? (
        <ChatView />
      ) : tab === 'dashboard' ? (
        <DashboardView />
      ) : (
        <DiagnosticsView />
      )}
    </div>
  )
}
