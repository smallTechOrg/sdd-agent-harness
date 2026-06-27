'use client'

import { useState } from 'react'

import {
  ComingSoonPanel,
  ConnectDatabaseButton,
} from '@/components/ComingSoon'
import MessageThread from '@/components/MessageThread'
import QuestionInput from '@/components/QuestionInput'
import UploadDropzone from '@/components/UploadDropzone'
import { ApiError, askQuestion } from '@/lib/api'
import type { ChatMessage, Dataset } from '@/lib/types'

let idCounter = 0
function nextId(prefix: string) {
  idCounter += 1
  return `${prefix}-${idCounter}`
}

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [conversationId, setConversationId] = useState<string | undefined>(undefined)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pending, setPending] = useState(false)

  async function handleAsk(question: string) {
    if (!dataset) return

    const userMsg: ChatMessage = {
      id: nextId('user'),
      role: 'user',
      content: question,
      chart: null,
    }
    const pendingId = nextId('assistant')
    const pendingMsg: ChatMessage = {
      id: pendingId,
      role: 'assistant',
      content: '',
      chart: null,
      pending: true,
    }
    setMessages(prev => [...prev, userMsg, pendingMsg])
    setPending(true)

    try {
      const res = await askQuestion({
        datasetId: dataset.dataset_id,
        question,
        conversationId,
      })
      // Persist the conversation id from the first turn onward.
      setConversationId(res.conversation_id)
      setMessages(prev =>
        prev.map(m =>
          m.id === pendingId
            ? {
                ...m,
                pending: false,
                content: res.answer,
                chart: res.chart,
              }
            : m,
        ),
      )
    } catch (e) {
      const isNetwork = !(e instanceof ApiError)
      const content = isNetwork
        ? 'Network error — is the server running?'
        : "I couldn't answer that — try rephrasing."
      setMessages(prev =>
        prev.map(m =>
          m.id === pendingId
            ? { ...m, pending: false, isError: true, content }
            : m,
        ),
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            DC
          </span>
          <h1 className="text-lg font-semibold tracking-tight text-gray-900">
            DataChat
          </h1>
        </div>
        <ConnectDatabaseButton />
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="hidden w-80 shrink-0 flex-col gap-5 overflow-y-auto border-r border-gray-200 bg-white px-4 py-5 md:flex">
          <UploadDropzone dataset={dataset} onUploaded={setDataset} />
          <div className="mt-auto">
            <ComingSoonPanel />
          </div>
        </aside>

        {/* Chat */}
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Mobile upload (sidebar is hidden on small screens) */}
          <div className="border-b border-gray-200 bg-white px-4 py-3 md:hidden">
            <UploadDropzone dataset={dataset} onUploaded={setDataset} />
          </div>

          <MessageThread messages={messages} hasDataset={!!dataset} />
          <QuestionInput
            disabled={!dataset}
            pending={pending}
            onAsk={handleAsk}
          />
        </main>
      </div>
    </div>
  )
}
