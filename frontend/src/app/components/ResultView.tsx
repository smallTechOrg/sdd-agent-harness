'use client'

import { useState } from 'react'
import type { Analysis } from './api'

export function ResultView({
  analysis,
  loading,
  error,
}: {
  analysis: Analysis | null
  loading: boolean
  error: string | null
}) {
  const failed = analysis?.status === 'failed'

  return (
    <section
      aria-labelledby="result-heading"
      aria-live="polite"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white"
        >
          3
        </span>
        <h2 id="result-heading" className="text-lg font-semibold text-slate-900">
          Result
        </h2>
      </div>

      {/* Loading */}
      {loading && (
        <div className="mt-6 flex items-center gap-3 text-slate-600">
          <svg className="h-5 w-5 animate-spin text-indigo-600" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span className="text-sm">Analyzing your data — writing and running pandas code…</span>
        </div>
      )}

      {/* Error (transport / HTTP error, not a graceful failed-analysis body) */}
      {!loading && error && (
        <p role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {/* Empty */}
      {!loading && !error && !analysis && (
        <p className="mt-6 text-sm text-slate-500">
          Your answer will appear here, along with the exact pandas code that was run and its output —
          so you can verify it yourself.
        </p>
      )}

      {/* Populated (completed or gracefully failed) */}
      {!loading && !error && analysis && (
        <div className="mt-6 space-y-5">
          <div
            className={`rounded-xl border px-4 py-4 ${
              failed ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-slate-50'
            }`}
          >
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {failed ? "Couldn't complete this analysis" : 'Answer'}
            </h3>
            <p
              className={`mt-2 whitespace-pre-wrap text-base leading-relaxed ${
                failed ? 'text-amber-900' : 'text-slate-900'
              }`}
            >
              {analysis.answer || (failed ? 'The analysis did not complete.' : 'No answer was returned.')}
            </p>
          </div>

          {/* Analysis code — ALWAYS shown, expanded by default. Core "show its work". */}
          <Disclosure title="Analysis code (pandas)" defaultOpen>
            {analysis.code ? (
              <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm leading-relaxed text-slate-100">
                <code>{analysis.code}</code>
              </pre>
            ) : (
              <p className="text-sm text-slate-500">No code was produced for this attempt.</p>
            )}
          </Disclosure>

          {/* Steps / captured output. */}
          <Disclosure title="Steps / output">
            {analysis.steps ? (
              <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-800">
                <code>{analysis.steps}</code>
              </pre>
            ) : (
              <p className="text-sm text-slate-500">No output was captured for this attempt.</p>
            )}
          </Disclosure>
        </div>
      )}
    </section>
  )
}

function Disclosure({
  title,
  defaultOpen = false,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-slate-200">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-xl px-4 py-3 text-left text-sm font-medium text-slate-800 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        {title}
        <svg
          className={`h-4 w-4 text-slate-500 transition-transform ${open ? 'rotate-90' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      {open && <div className="border-t border-slate-200 px-4 py-3">{children}</div>}
    </div>
  )
}
