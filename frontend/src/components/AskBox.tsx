'use client'

import { useState } from 'react'

interface AskBoxProps {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  running: boolean
}

export function AskBox({ value, onChange, onSubmit, running }: AskBoxProps) {
  const [showDeepHint, setShowDeepHint] = useState(false)

  return (
    <section aria-label="Ask a question" className="space-y-2">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (value.trim() && !running) onSubmit()
        }}
        className="flex flex-col gap-3 sm:flex-row sm:items-stretch"
      >
        <label htmlFor="ask-input" className="sr-only">
          Ask a question about your data
        </label>
        <input
          id="ask-input"
          type="text"
          data-testid="ask-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={running}
          placeholder="Ask a question, e.g. “What is total revenue by region?”"
          className="flex-1 rounded-lg border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-50"
        />
        <button
          type="submit"
          data-testid="ask-button"
          disabled={running || !value.trim()}
          className="rounded-lg bg-indigo-600 px-6 py-3 text-base font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? 'Working…' : 'Ask'}
        </button>
      </form>

      {/* Phase 4 stub: Deep analysis toggle — disabled, clearly labelled. */}
      <div className="flex items-center gap-2">
        <label
          className="inline-flex cursor-not-allowed items-center gap-2 text-sm text-slate-400"
          onMouseEnter={() => setShowDeepHint(true)}
          onMouseLeave={() => setShowDeepHint(false)}
        >
          <input
            type="checkbox"
            disabled
            aria-disabled="true"
            className="h-4 w-4 cursor-not-allowed rounded border-slate-300"
          />
          Deep analysis (plan &amp; iterate)
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            Phase 4
          </span>
        </label>
        {showDeepHint && (
          <span className="text-xs text-slate-400">
            Bounded multi-step planning arrives in Phase 4.
          </span>
        )}
      </div>
    </section>
  )
}
