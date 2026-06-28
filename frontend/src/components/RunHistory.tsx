'use client'

import type { RunRecord } from '../lib/api'

interface RunHistoryProps {
  runs: RunRecord[]
  loading: boolean
  error: string | null
  activeRunId: string | null
  onReopen: (run: RunRecord) => void
}

// Format an ISO timestamp into a short, locale-friendly label. Falls back to the
// raw string if it can't be parsed (never throws in render).
function formatWhen(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

// The run-history list for the selected dataset (Phase 2). Each item is a prior
// question; clicking re-opens that run's persisted answer in the existing
// AnswerPanel — NO LLM call, no ask spinner (pure DB read upstream). Loading /
// empty / error are distinct states; empty is a normal note, error is red.
export function RunHistory({ runs, loading, error, activeRunId, onReopen }: RunHistoryProps) {
  return (
    <section
      data-testid="run-history"
      className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-gray-900">Run history</h2>
      <p className="mt-0.5 text-xs text-gray-400">
        Past questions for this dataset — click to re-open instantly (no new question asked).
      </p>

      <div className="mt-3">
        {loading ? (
          <ul data-testid="run-history-loading" className="space-y-2" aria-busy="true">
            {[0, 1].map((i) => (
              <li
                key={i}
                className="h-9 animate-pulse rounded-lg border border-gray-100 bg-gray-50"
              />
            ))}
          </ul>
        ) : error ? (
          <p
            data-testid="run-history-error"
            role="alert"
            className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs font-medium text-red-700"
          >
            {error}
          </p>
        ) : runs.length === 0 ? (
          <p data-testid="run-history-empty" className="text-xs text-gray-400">
            No questions yet for this dataset.
          </p>
        ) : (
          <ul data-testid="run-history-list" className="space-y-2">
            {runs.map((run) => {
              const active = run.run_id === activeRunId
              const failed = run.status === 'failed'
              return (
                <li key={run.run_id}>
                  <button
                    type="button"
                    data-testid="run-history-item"
                    data-active={active ? 'true' : 'false'}
                    aria-current={active ? 'true' : undefined}
                    onClick={() => onReopen(run)}
                    className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                      active
                        ? 'border-blue-300 bg-blue-50 ring-1 ring-blue-200'
                        : 'border-gray-200 bg-white hover:border-blue-200 hover:bg-blue-50/40'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                          failed ? 'bg-red-400' : active ? 'bg-blue-500' : 'bg-gray-300'
                        }`}
                      />
                      <span className="min-w-0 flex-1">
                        <span
                          className={`block truncate text-sm font-medium ${
                            active ? 'text-blue-900' : 'text-gray-800'
                          }`}
                        >
                          {run.question}
                        </span>
                        <span className="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
                          <span>{formatWhen(run.created_at)}</span>
                          {failed && (
                            <span className="font-medium text-red-500">failed</span>
                          )}
                        </span>
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
