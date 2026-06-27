'use client'

import AgentMessage, { type AgentMessageProps } from './AgentMessage'

export interface Message {
  id: string
  role: 'user' | 'agent'
  content?: string
  agentData?: AgentMessageProps
}

interface ChatThreadProps {
  messages: Message[]
}

export default function ChatThread({ messages }: ChatThreadProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm italic text-gray-400">
          Upload a file and ask a question to get started
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
      {messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-xs rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2.5 text-sm text-white">
                {msg.content}
              </div>
            </div>
          )
        }

        return (
          <div key={msg.id} className="flex justify-start">
            <div className="max-w-2xl rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
              <AgentMessage {...(msg.agentData ?? {})} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
