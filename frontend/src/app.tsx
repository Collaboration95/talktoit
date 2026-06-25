import { useState } from 'react'
import { ChatView } from '@/components/chat-view'
import { DashboardView } from '@/components/dashboard-view'

export function App() {
  const [tab, setTab] = useState<'chat' | 'dashboard'>('chat')
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-3xl gap-4 px-4 py-3">
          <button
            onClick={() => setTab('chat')}
            className={`text-sm font-medium ${tab === 'chat' ? 'text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
          >
            Chat
          </button>
          <button
            onClick={() => setTab('dashboard')}
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
