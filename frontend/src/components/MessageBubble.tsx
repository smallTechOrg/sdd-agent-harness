'use client'

import ChartRenderer from './ChartRenderer'
import type { ChatMessage } from '@/lib/types'

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={[
            'rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm',
            isUser
              ? 'bg-blue-600 text-white rounded-br-sm'
              : message.isError
                ? 'border border-red-200 bg-red-50 text-red-700 rounded-bl-sm'
                : 'border border-gray-200 bg-white text-gray-800 rounded-bl-sm',
          ].join(' ')}
        >
          {message.pending ? (
            <ThinkingIndicator />
          ) : (
            <span className="whitespace-pre-wrap">{message.content}</span>
          )}
        </div>

        {!isUser && message.chart && <ChartRenderer spec={message.chart} />}
      </div>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-gray-500"
      aria-label="Thinking"
      role="status"
    >
      <span>Thinking</span>
      <span className="inline-flex gap-1">
        <Dot delay="0ms" />
        <Dot delay="150ms" />
        <Dot delay="300ms" />
      </span>
    </span>
  )
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 motion-reduce:animate-none"
      style={{ animationDelay: delay }}
    />
  )
}
