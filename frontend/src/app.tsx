import { useState } from 'react'
import { ChatView } from '@/components/chat-view'
import { DashboardView } from '@/components/dashboard-view'

/** Resolve the top-level view from the URL on first load (backwards compatible). */
function initialTab(): 'chat' | 'dashboard' {
  const tab = new URLSearchParams(window.location.search).get('tab')
  return tab === 'workouts' || tab === 'dashboard' ? 'dashboard' : 'chat'
}

/** Keep the URL tab in sync with the visible view without dropping dashboard state. */
function pushTab(tab: 'chat' | 'dashboard') {
  const params = new URLSearchParams(window.location.search)
  params.set('tab', tab)
  window.history.pushState({}, '', `?${params.toString()}`)
}

export function App() {
  const [tab, setTab] = useState<'chat' | 'dashboard'>(initialTab)

  const selectTab = (next: 'chat' | 'dashboard') => {
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
        </div>
      </nav>
      {tab === 'chat' ? <ChatView /> : <DashboardView />}
    </div>
  )
}
