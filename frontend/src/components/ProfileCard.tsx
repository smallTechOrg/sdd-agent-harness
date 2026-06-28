'use client'

import type { DatasetResponse } from '../lib/types'
import { SuggestedQuestions } from './SuggestedQuestions'

interface ProfileCardProps {
  dataset: DatasetResponse
  onPickQuestion: (q: string) => void
}

function fmtRange(min: unknown, max: unknown): string {
  if (min == null && max == null) return '—'
  const m = min == null ? '—' : String(min)
  const x = max == null ? '—' : String(max)
  return `${m} … ${x}`
}

export function ProfileCard({ dataset, onPickQuestion }: ProfileCardProps) {
  const { profile, filename, row_count, column_count, suggested_questions } =
    dataset
  const columns = profile?.columns ?? []
  const flags = profile?.quality_flags ?? []

  return (
    <section
      aria-label="Dataset profile"
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
      data-testid="profile-card"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-100 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{filename}</h2>
          <p className="text-sm text-slate-500" data-testid="profile-counts">
            <span className="font-medium text-slate-700">
              {row_count.toLocaleString()}
            </span>{' '}
            rows ×{' '}
            <span className="font-medium text-slate-700">{column_count}</span>{' '}
            columns
          </p>
        </div>
        {flags.length > 0 && (
          <div className="flex flex-wrap gap-2" data-testid="quality-flags">
            {flags.map((f, i) => (
              <span
                key={i}
                className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800"
                title={`${f.column}: ${f.issue}`}
              >
                {f.column}: {f.issue}
              </span>
            ))}
          </div>
        )}
      </header>

      <div className="overflow-x-auto px-2 py-2">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-2 font-medium">Column</th>
              <th className="px-4 py-2 font-medium">Type</th>
              <th className="px-4 py-2 font-medium">Missing</th>
              <th className="px-4 py-2 font-medium">Distinct</th>
              <th className="px-4 py-2 font-medium">Range / Examples</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {columns.map((c) => {
              const labels = c.example_labels ?? []
              const hasRange = c.min != null || c.max != null
              return (
                <tr key={c.name} className="text-slate-700">
                  <td className="px-4 py-2 font-medium text-slate-900">
                    {c.name}
                  </td>
                  <td className="px-4 py-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
                      {c.dtype}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {c.missing_pct != null
                      ? `${c.missing_pct.toFixed(1)}%`
                      : '—'}
                  </td>
                  <td className="px-4 py-2">{c.distinct_count ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-500">
                    {hasRange ? (
                      fmtRange(c.min, c.max)
                    ) : labels.length > 0 ? (
                      <span className="flex flex-wrap gap-1">
                        {labels.slice(0, 6).map((l, i) => (
                          <span
                            key={i}
                            className="rounded bg-slate-100 px-1.5 py-0.5 text-xs"
                          >
                            {l}
                          </span>
                        ))}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {suggested_questions && suggested_questions.length > 0 && (
        <div className="border-t border-slate-100 px-6 py-4">
          <SuggestedQuestions
            questions={suggested_questions}
            onPick={onPickQuestion}
          />
        </div>
      )}
    </section>
  )
}
