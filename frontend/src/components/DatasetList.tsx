'use client'

import type { DatasetSummary } from '../lib/api'

interface DatasetListProps {
  datasets: DatasetSummary[]
  activeId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
}

// The REAL "Past datasets" list (Phase 2). Populated from GET /datasets, newest
// first. Loading / empty / error are all distinct states — empty is a normal,
// non-red friendly note (NOT a stub badge), error is red.
export function DatasetList({ datasets, activeId, loading, error, onSelect }: DatasetListProps) {
  if (loading) {
    return (
      <ul data-testid="dataset-list-loading" className="space-y-2" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <li
            key={i}
            className="flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-gray-300" />
            <span className="h-3 flex-1 animate-pulse rounded bg-gray-200" />
          </li>
        ))}
      </ul>
    )
  }

  if (error) {
    return (
      <p
        data-testid="dataset-list-error"
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs font-medium text-red-700"
      >
        {error}
      </p>
    )
  }

  if (datasets.length === 0) {
    return (
      <p data-testid="dataset-list-empty" className="text-xs text-gray-400">
        No past datasets yet — upload one to begin.
      </p>
    )
  }

  return (
    <ul data-testid="dataset-list" className="space-y-2">
      {datasets.map((d) => {
        const active = d.id === activeId
        const failed = d.status !== 'ready'
        return (
          <li key={d.id}>
            <button
              type="button"
              data-testid="dataset-list-item"
              data-active={active ? 'true' : 'false'}
              aria-current={active ? 'true' : undefined}
              onClick={() => onSelect(d.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                active
                  ? 'border-blue-300 bg-blue-50 ring-1 ring-blue-200'
                  : 'border-gray-200 bg-white hover:border-blue-200 hover:bg-blue-50/40'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    failed ? 'bg-red-400' : active ? 'bg-blue-500' : 'bg-gray-300'
                  }`}
                />
                <span
                  // Only the ACTIVE item carries the Phase-1 `current-dataset`
                  // testid, so the page renders exactly one such element.
                  data-testid={active ? 'current-dataset' : undefined}
                  className={`truncate text-sm font-medium ${
                    active ? 'text-blue-900' : 'text-gray-800'
                  }`}
                >
                  {d.name}
                </span>
                {active && (
                  <span className="ml-auto shrink-0 text-[10px] font-semibold uppercase tracking-wide text-blue-600">
                    active
                  </span>
                )}
              </div>
              <div className={`mt-0.5 text-xs ${active ? 'text-blue-600' : 'text-gray-500'}`}>
                {d.row_count.toLocaleString('en-US')} rows ·{' '}
                {d.question_count.toLocaleString('en-US')}{' '}
                {d.question_count === 1 ? 'question' : 'questions'}
                {failed && <span className="ml-1 text-red-500">· {d.status}</span>}
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
