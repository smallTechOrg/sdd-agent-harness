'use client'

import { DataChart } from './DataChart'
import type { ChartSpec } from './DataChart'
import { StubBadge } from './StubBadge'

export interface QueryResponse {
  query_run_id: string
  status: 'completed' | 'failed'
  sql?: string
  chart_spec?: ChartSpec
  insight?: string
  error?: string
}

interface AnswerCardProps {
  question: string
  answer: QueryResponse | null
  loading: boolean
}

export function AnswerCard({ question, answer, loading }: AnswerCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      {/* Question header */}
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
        <p className="text-sm font-medium text-gray-700">{question}</p>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="px-4 py-6 flex items-center gap-3 text-gray-400">
          <svg
            className="animate-spin h-4 w-4 text-indigo-500"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-sm">Thinking&hellip;</span>
        </div>
      )}

      {/* Answer content */}
      {!loading && answer && (
        <div className="divide-y divide-gray-100">
          {/* Failed state */}
          {answer.status === 'failed' && (
            <div className="px-4 py-4 bg-amber-50 border-l-4 border-amber-400">
              <p className="text-sm font-medium text-amber-800 mb-1">Query failed</p>
              <p className="text-sm text-amber-700">{answer.error ?? 'An unknown error occurred.'}</p>
            </div>
          )}

          {/* SQL block */}
          {answer.sql && (
            <div className="px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">SQL Query</p>
              <pre className="rounded-lg bg-gray-900 text-green-400 font-mono text-xs p-4 overflow-x-auto whitespace-pre-wrap break-words">
                <code>{answer.sql}</code>
              </pre>
            </div>
          )}

          {/* Chart */}
          {answer.chart_spec && (
            <div className="px-4 py-4">
              {answer.chart_spec.title && (
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                  Chart — {answer.chart_spec.title}
                </p>
              )}
              {!answer.chart_spec.title && (
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Chart</p>
              )}
              <DataChart chartSpec={answer.chart_spec} />
            </div>
          )}

          {/* Insight */}
          {answer.insight && (
            <div className="px-4 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Insight</p>
              <p className="text-sm text-gray-700 leading-relaxed">{answer.insight}</p>
            </div>
          )}

          {/* Stub: Pin to Dashboard */}
          <div className="px-4 py-3 bg-gray-50 flex items-center">
            <button
              type="button"
              onClick={() => alert('Coming soon — dashboard pinning is planned for Phase 2.')}
              className="flex items-center gap-1.5 text-sm text-gray-400 cursor-not-allowed opacity-75"
              title="Coming in Phase 2 — save this chart to your dashboard."
            >
              Pin to Dashboard
              <StubBadge label="Phase 2" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
