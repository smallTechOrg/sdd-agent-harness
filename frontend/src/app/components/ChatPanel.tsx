'use client'

import { useEffect, useRef, useState } from 'react'
import { Answer, Dataset, Turn, friendlyError } from './types'
import AnswerChart from './AnswerChart'

interface Props {
  dataset: Dataset | null
}

export default function ChatPanel({ dataset }: Props) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const historyRef = useRef<HTMLDivElement>(null)

  // Reset the conversation whenever a new dataset is loaded.
  useEffect(() => {
    setTurns([])
    setError(null)
    setQuestion('')
  }, [dataset?.dataset_id])

  // Keep the newest turn in view.
  useEffect(() => {
    historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, loading])

  const ready = Boolean(dataset)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!dataset || !question.trim() || loading) return
    const asked = question.trim()
    setLoading(true)
    setError(null)
    setQuestion('')
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: dataset.dataset_id, question: asked }),
      })
      const body = await res.json()
      if (!res.ok) {
        setError(friendlyError(body.detail?.code, body.detail?.message ?? `Request failed (${res.status})`))
        setQuestion(asked)
        return
      }
      const answer = body.data as Answer
      setTurns(prev => [...prev, { question: asked, answer }])
    } catch {
      setError('Network error — is the server running?')
      setQuestion(asked)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="flex h-full flex-col rounded-xl border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-100 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">Ask a question</h2>
      </div>

      <div ref={historyRef} className="flex-1 space-y-5 overflow-y-auto px-5 py-5" style={{ minHeight: 320 }}>
        {!ready && (
          <div className="flex h-full flex-col items-center justify-center text-center text-gray-400">
            <p className="text-sm font-medium text-gray-500">Upload a CSV to begin</p>
            <p className="mt-1 text-xs">Then ask anything in plain English, like &ldquo;total revenue by region&rdquo;.</p>
          </div>
        )}

        {ready && turns.length === 0 && !loading && (
          <div className="flex h-full flex-col items-center justify-center text-center text-gray-400">
            <p className="text-sm">Ask your first question about <span className="font-medium text-gray-600">{dataset!.name}</span>.</p>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white">
                {turn.question}
              </p>
            </div>
            <div className="rounded-2xl rounded-bl-sm bg-gray-50 px-4 py-3">
              <p className="whitespace-pre-wrap text-sm text-gray-800">{turn.answer.answer_text}</p>
              <div className="mt-3">
                <AnswerChart spec={turn.answer.chart_spec} />
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner /> Thinking…
          </div>
        )}
      </div>

      {error && (
        <div className="mx-5 mb-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-gray-100 p-3">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          disabled={!ready || loading}
          placeholder={ready ? 'Ask about your data…' : 'Upload a CSV to begin'}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
        />
        <button
          type="submit"
          disabled={!ready || loading || !question.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Asking…' : 'Ask'}
        </button>
      </form>
    </section>
  )
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-gray-500" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
