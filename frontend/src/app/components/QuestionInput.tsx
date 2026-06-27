'use client'

import { useState } from 'react'
import { ComingSoon } from './ComingSoon'

export function QuestionInput({
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
      aria-labelledby="question-heading"
      className={`rounded-2xl border bg-white p-6 shadow-sm transition-opacity ${
        enabled ? 'border-slate-200' : 'border-slate-200 opacity-60'
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold text-white ${
            enabled ? 'bg-indigo-600' : 'bg-slate-300'
          }`}
        >
          2
        </span>
        <h2 id="question-heading" className="text-lg font-semibold text-slate-900">
          Ask a question
        </h2>
      </div>

      {!enabled && (
        <p className="mt-2 text-sm text-slate-500">Upload a CSV above to start asking questions.</p>
      )}

      <form onSubmit={submit} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-stretch">
        <label htmlFor="question" className="sr-only">
          Your question about the data
        </label>
        <input
          id="question"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!enabled || loading}
          placeholder="e.g. What is the average amount per region?"
          className="flex-1 rounded-xl border border-slate-300 px-4 py-3 text-base text-slate-900 placeholder:text-slate-400 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={!canAsk}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 text-base font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? (
            <>
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Analyzing…
            </>
          ) : (
            'Ask'
          )}
        </button>
      </form>

      <label className="mt-3 inline-flex cursor-not-allowed items-center gap-2 text-sm text-slate-400">
        <input type="checkbox" disabled className="accent-slate-400" />
        Visualize result
        <ComingSoon />
      </label>
    </section>
  )
}
