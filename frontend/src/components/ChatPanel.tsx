'use client'

import { useEffect, useRef, useState } from 'react'
import { AnswerCard } from './AnswerCard'
import type { QueryResponse } from './AnswerCard'

interface ChatSession {
  session_id: string
  table_name: string
}

interface Message {
  question: string
  answer: QueryResponse | null
  loading: boolean
}

interface ChatPanelProps {
  session: ChatSession | null
}

const MAX_CHARS = 2000

export function ChatPanel({ session }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const charsLeft = MAX_CHARS - question.length
  const nearLimit = charsLeft <= 200

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault()
    if (!session || !question.trim() || submitting) return

    const q = question.trim()
    setQuestion('')
    setSubmitting(true)

    const idx = messages.length
    setMessages((prev) => [...prev, { question: q, answer: null, loading: true }])

    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: session.session_id, question: q }),
      })
      const data = await res.json()

      let answer: QueryResponse
      if (!res.ok) {
        const msg =
          data.detail?.message ??
          data.error?.message ??
          `Request failed (${res.status})`
        answer = {
          query_run_id: '',
          status: 'failed',
          error: msg,
        }
      } else if (data.ok) {
        answer = data.data as QueryResponse
      } else {
        answer = {
          query_run_id: '',
          status: 'failed',
          error: data.error?.message ?? 'Unknown error.',
        }
      }

      setMessages((prev) => {
        const updated = [...prev]
        updated[idx] = { question: q, answer, loading: false }
        return updated
      })
    } catch {
      setMessages((prev) => {
        const updated = [...prev]
        updated[idx] = {
          question: q,
          answer: {
            query_run_id: '',
            status: 'failed',
            error: 'Network error — is the server running?',
          },
          loading: false,
        }
        return updated
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <h2 className="text-base font-semibold text-gray-800 mb-4">Ask a Question</h2>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
        {messages.length === 0 && !session && (
          <div className="flex items-center justify-center h-32 text-sm text-gray-400 text-center">
            Upload a CSV file to get started.
          </div>
        )}
        {messages.length === 0 && session && (
          <div className="flex items-center justify-center h-32 text-sm text-gray-400 text-center">
            Ask a question about <span className="font-medium text-gray-600 mx-1">{session.table_name}</span> to get started.
          </div>
        )}
        {messages.map((msg, i) => (
          <AnswerCard
            key={i}
            question={msg.question}
            answer={msg.answer}
            loading={msg.loading}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input form */}
      <form onSubmit={handleAsk} className="flex flex-col gap-2">
        <div className="relative">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value.slice(0, MAX_CHARS))}
            disabled={!session || submitting}
            placeholder={
              session
                ? `Ask about ${session.table_name}…`
                : 'Upload a CSV file first…'
            }
            maxLength={MAX_CHARS}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400 pr-16"
          />
          {nearLimit && (
            <span
              className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs ${
                charsLeft <= 50 ? 'text-red-500' : 'text-amber-500'
              }`}
            >
              {charsLeft}
            </span>
          )}
        </div>
        <button
          type="submit"
          disabled={!session || !question.trim() || submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Thinking…' : 'Ask'}
        </button>
      </form>
    </div>
  )
}
