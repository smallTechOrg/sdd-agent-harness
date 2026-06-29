'use client'

import { useState } from 'react'

export function QuestionPanel({
  enabled,
  loading,
  onAsk,
}: {
  enabled: boolean
  loading: boolean
  onAsk: (question: string) => void
}) {
  const [question, setQuestion] = useState('')
  const canAsk = enabled && !loading && question.trim().length > 0

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!canAsk) return
    onAsk(question.trim())
  }

  return (
    <section
      data-testid="question-panel"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-gray-800">2 · Ask a question</h2>
      <form onSubmit={submit} className="mt-3 flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          disabled={!enabled || loading}
          data-testid="question-input"
          placeholder={
            enabled ? 'e.g. What is the total revenue?' : 'Upload a CSV first to ask a question'
          }
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
        />
        <button
          type="submit"
          disabled={!canAsk}
          data-testid="ask-button"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
          )}
          {loading ? 'Working…' : 'Ask'}
        </button>
      </form>
      {!enabled && (
        <p className="mt-2 text-xs text-gray-400" data-testid="ask-hint">
          The question box unlocks once a dataset is loaded.
        </p>
      )}
    </section>
  )
}
