'use client'

import { useState } from 'react'
import { ApiError, ask, type AskResult, type Dataset } from '../lib/api'
import ErrorBanner from './ErrorBanner'

interface AskBoxProps {
  dataset: Dataset | null
  onResult: (result: AskResult) => void
  onCompleted: () => void
}

function messageFor(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 400) {
      return "The model couldn't generate valid SQL for that question — try rephrasing."
    }
    if (e.status === 502) {
      return 'Analysis service is temporarily unavailable — please retry.'
    }
    return e.message
  }
  return 'Something went wrong — please try again.'
}

export default function AskBox({ dataset, onResult, onCompleted }: AskBoxProps) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault()
    if (!dataset || !question.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await ask(dataset.id, question.trim())
      onResult(result)
    } catch (err) {
      setError(messageFor(err))
    } finally {
      setLoading(false)
      onCompleted()
    }
  }

  return (
    <form onSubmit={handleAsk} className="space-y-3">
      <label htmlFor="ask-input" className="block text-sm font-medium text-gray-700">
        {dataset ? (
          <>
            Ask a question about <span className="font-semibold">{dataset.name}</span>
          </>
        ) : (
          'Select a dataset to ask a question'
        )}
      </label>
      <textarea
        id="ask-input"
        rows={2}
        value={question}
        onChange={e => setQuestion(e.target.value)}
        disabled={!dataset || loading}
        placeholder="e.g. What were total sales by region?"
        className="w-full rounded-lg border border-gray-300 p-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-100"
      />
      <button
        type="submit"
        disabled={!dataset || loading || !question.trim()}
        className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? 'Analyzing…' : 'Ask'}
      </button>
      {error && <ErrorBanner message={error} />}
    </form>
  )
}
