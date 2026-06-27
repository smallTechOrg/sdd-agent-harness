'use client'

import { useEffect, useRef } from 'react'

import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/lib/types'

interface Props {
  messages: ChatMessage[]
  hasDataset: boolean
}

export default function MessageThread({ messages, hasDataset }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to newest on any change to the thread.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 text-2xl">
          📊
        </div>
        <h2 className="text-lg font-semibold text-gray-800">
          {hasDataset ? 'Ask a question about your data' : 'Start with your data'}
        </h2>
        <p className="mt-2 max-w-sm text-sm text-gray-500">
          {hasDataset
            ? 'Try “what were total sales by region?” — the agent computes the answer locally and picks a chart for you.'
            : 'Upload a CSV or Excel file to start chatting with your data.'}
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
