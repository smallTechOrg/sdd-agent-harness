'use client'

import type { AskResult, ResultRow } from '@/lib/api'
import { Chart } from '@/components/Chart'
import { SummaryTable } from '@/components/SummaryTable'
import { Followups } from '@/components/Followups'

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString()
  return String(value)
}

function ResultTable({ rows }: { rows: ResultRow[] }) {
  if (!rows.length) return null
  const columns = Object.keys(rows[0])
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200" data-testid="result-table">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {columns.map(c => (
              <th key={c} className="px-3 py-2 text-left font-medium text-gray-600">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map(c => (
                <td key={c} className="px-3 py-2 font-mono text-gray-800">
                  {formatCell(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AnswerPanel({
  loading,
  result,
  error,
  onFollowup,
}: {
  loading: boolean
  result: AskResult | null
  error: string | null
  onFollowup: (question: string) => void
}) {
  return (
    <section
      data-testid="answer-panel"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-gray-800">3 · Answer</h2>

      {/* Loading */}
      {loading && (
        <div className="mt-4 flex items-center gap-3 text-sm text-gray-500" data-testid="answer-working">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" aria-hidden />
          Working… running the query locally in DuckDB.
        </div>
      )}

      {/* Transport / network or 4xx error from the request itself */}
      {!loading && error && (
        <div
          data-testid="answer-error"
          role="alert"
          className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {/* A run that came back failed (status: failed) — surface it, never fabricate a number */}
      {!loading && !error && result && result.status === 'failed' && (
        <div
          data-testid="answer-failed"
          role="alert"
          className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          <p className="font-medium">The query could not be completed — no number was verified.</p>
          <p className="mt-1 text-red-600">{result.error ?? 'The agent was unable to answer this question.'}</p>
          {result.sql && (
            <pre className="mt-3 overflow-x-auto rounded bg-white/70 p-2 font-mono text-xs text-red-800">
              {result.sql}
            </pre>
          )}
        </div>
      )}

      {/* Successful run */}
      {!loading && !error && result && result.status === 'completed' && (
        <div className="mt-4 space-y-4" data-testid="answer-completed">
          <div>
            {result.flagged && (
              <span
                data-testid="best-guess-badge"
                className="mb-2 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-700"
              >
                ⚠ Best guess
              </span>
            )}
            <p className="text-base leading-relaxed text-gray-900" data-testid="answer-text">
              {result.answer}
            </p>
          </div>

          {result.sql && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Exact SQL
              </div>
              <pre
                data-testid="answer-sql"
                className="overflow-x-auto rounded-lg border border-gray-200 bg-gray-900 p-3 font-mono text-xs leading-relaxed text-gray-100"
              >
                {result.sql}
              </pre>
            </div>
          )}

          {/* Chart — rendered from the backend chart spec; renders nothing when null. */}
          {result.chart && result.result && result.result.length > 0 && (
            <Chart spec={result.chart} rows={result.result} />
          )}

          {/* Rich summary table when present; else fall back to the basic result table. */}
          {result.summary_table ? (
            <SummaryTable table={result.summary_table} />
          ) : (
            result.result && result.result.length > 0 && <ResultTable rows={result.result} />
          )}

          {/* Follow-up chips — clicking one submits it as the next question. */}
          <Followups
            followups={result.followups}
            disabled={loading}
            onPick={onFollowup}
          />
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !result && (
        <p className="mt-6 text-center text-sm text-gray-400" data-testid="answer-empty">
          Your answer, the exact SQL, and a result table will appear here.
        </p>
      )}
    </section>
  )
}
