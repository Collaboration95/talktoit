import { lazy, Suspense, useEffect, useState } from 'react'
import { ChatView } from '@/components/chat-view'

const DashboardView = lazy(() =>
  import('@/components/dashboard-view').then(({ DashboardView: view }) => ({ default: view })),
)
const DiagnosticsView = lazy(() =>
  import('@/components/diagnostics-view').then(({ DiagnosticsView: view }) => ({ default: view })),
)
const SettingsView = lazy(() =>
  import('@/components/settings-view').then(({ SettingsView: view }) => ({ default: view })),
)

function TabFallback() {
  return (
    <div
      className="mx-auto flex min-h-64 max-w-4xl items-center justify-center px-4 py-6 text-gray-500"
      data-testid="tab-loading"
      role="status"
    >
      Loading view…
    </div>
  )
}

/** Resolve the top-level view from the URL on first load (backwards compatible). */
function initialTab(): 'chat' | 'dashboard' | 'diagnostics' | 'settings' {
  const tab = new URLSearchParams(window.location.search).get('tab')
  if (tab === 'workouts' || tab === 'dashboard') return 'dashboard'
  if (tab === 'diagnostics') return 'diagnostics'
  if (tab === 'settings') return 'settings'
  return 'chat'
}

/** Keep the URL tab in sync with the visible view without dropping dashboard state. */
function pushTab(tab: 'chat' | 'dashboard' | 'diagnostics' | 'settings') {
  const params = new URLSearchParams(window.location.search)
  params.set('tab', tab)
  window.history.pushState({}, '', `?${params.toString()}`)
}

export function App() {
  const [tab, setTab] = useState<'chat' | 'dashboard' | 'diagnostics' | 'settings'>(initialTab)

  // Browser Back/Forward re-navigates the URL tab; re-derive the view from the
  // query string so the address bar and the visible tab never diverge.
  useEffect(() => {
    const onPopState = () => setTab(initialTab())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const selectTab = (next: 'chat' | 'dashboard' | 'diagnostics' | 'settings') => {
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
          <button
            onClick={() => selectTab('settings')}
            className={`text-sm font-medium ${tab === 'settings' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Settings
          </button>
        </div>
      </nav>
      <Suspense fallback={<TabFallback />}>
        {tab === 'chat' ? (
          <ChatView />
        ) : tab === 'dashboard' ? (
          <DashboardView />
        ) : tab === 'diagnostics' ? (
          <DiagnosticsView />
        ) : (
          <SettingsView />
        )}
      </Suspense>
    </div>
  )
}
