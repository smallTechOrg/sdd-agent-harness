'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ColumnSchema,
  type DatasetSummary,
} from '@/lib/api'

/**
 * Datasets / "Tables" card — REAL, multi-select in Phase 3.
 *
 * Fetches GET /datasets on mount and whenever `datasetsVersion` changes (the
 * parent bumps it after each upload and each completed ask, surfacing new /
 * derived datasets). Each row shows filename + rows×cols + format, a checkbox to
 * include the dataset in the next question, a "cols" toggle that lazily fetches
 * GET /datasets/{id} for the column schema, and a delete action with an inline
 * confirm → DELETE /datasets/{id}.
 *
 * Phase-3 sessions can span MULTIPLE datasets. Selection is now multi-select:
 *  - select one or more datasets to pin them for the next ask, OR
 *  - select none ("Let the agent pick") so the server's C19 selector chooses
 *    over all uploaded datasets.
 *
 * The filter tabs (All|Uploaded|Derived|This session) remain labelled stubs —
 * there are no derived datasets until Phase 4 — so they are shown disabled.
 */

const FILTERS = ['All', 'Uploaded', 'Derived', 'This session'] as const

interface ColsState {
  loading: boolean
  error: string | null
  columns: ColumnSchema[] | null
}

export function TablesCard({
  datasetsVersion,
  selectedDatasetIds,
  onToggleSelect,
  onClearSelection,
  onDeleted,
}: {
  datasetsVersion: number
  selectedDatasetIds: string[]
  onToggleSelect: (id: string) => void
  onClearSelection: () => void
  onDeleted: (id: string) => void
}) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Per-row "cols" expansion state, keyed by dataset id.
  const [colsById, setColsById] = useState<Record<string, ColsState>>({})
  // Which row is awaiting delete confirmation.
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.listDatasets()
      setDatasets(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load datasets.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, datasetsVersion])

  const toggleCols = useCallback(
    async (id: string) => {
      const current = colsById[id]
      if (current && !current.loading) {
        // Already loaded (or errored) → collapse by removing it.
        setColsById(prev => {
          const next = { ...prev }
          delete next[id]
          return next
        })
        return
      }
      setColsById(prev => ({ ...prev, [id]: { loading: true, error: null, columns: null } }))
      try {
        const detail = await api.getDataset(id)
        setColsById(prev => ({
          ...prev,
          [id]: { loading: false, error: null, columns: detail.columns_schema ?? [] },
        }))
      } catch (err) {
        setColsById(prev => ({
          ...prev,
          [id]: {
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load columns.',
            columns: null,
          },
        }))
      }
    },
    [colsById],
  )

  const confirmDelete = useCallback(
    async (id: string) => {
      setDeletingId(id)
      try {
        await api.deleteDataset(id)
        setConfirmingId(null)
        onDeleted(id)
        // Optimistic local removal in case the parent refresh lags.
        setDatasets(prev => prev.filter(d => d.id !== id))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete dataset.')
      } finally {
        setDeletingId(null)
      }
    },
    [onDeleted],
  )

  return (
    <section
      aria-labelledby="tables-heading"
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="tables-heading" className="text-sm font-semibold text-gray-800">
          Tables
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
          aria-label="Refresh datasets"
        >
          Refresh
        </button>
      </div>

      {/* Selection mode: explicit datasets vs. let the agent pick (C19). */}
      {datasets.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-3 py-2 text-xs">
          {selectedDatasetIds.length === 0 ? (
            <span className="font-medium text-gray-700">
              Let the agent pick the dataset(s)
            </span>
          ) : (
            <>
              <span className="font-medium text-gray-700">
                {selectedDatasetIds.length} dataset
                {selectedDatasetIds.length === 1 ? '' : 's'} selected
              </span>
              <button
                type="button"
                onClick={onClearSelection}
                className="rounded border border-gray-300 bg-white px-2 py-0.5 font-medium text-gray-600 hover:bg-gray-50"
              >
                Clear (let agent pick)
              </button>
            </>
          )}
        </div>
      )}

      {/* Filter tabs — still labelled stubs (no session/derived concept yet). */}
      <div
        role="group"
        aria-label="Dataset filters (coming in a later phase)"
        className="mb-3 flex flex-wrap gap-2"
      >
        {FILTERS.map((f, i) => (
          <button
            key={f}
            type="button"
            disabled
            aria-disabled="true"
            aria-pressed={i === 0 ? true : false}
            title="Filtering by origin/session arrives in a later phase"
            className={`cursor-not-allowed rounded-full border px-3 py-1 text-xs font-medium ${
              i === 0
                ? 'border-gray-300 bg-gray-100 text-gray-500'
                : 'border-gray-200 bg-white text-gray-400'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* States: loading / error / empty / list */}
      {loading && datasets.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 px-3 py-8 text-center text-xs text-gray-400">
          Loading datasets…
        </div>
      ) : error ? (
        <div
          role="alert"
          className="flex flex-col items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-6 text-center text-xs text-red-700"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded border border-red-300 bg-white px-2 py-0.5 font-medium text-red-700 hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      ) : datasets.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 px-3 py-8 text-center text-xs text-gray-400">
          No datasets yet. Upload a CSV below to get started.
        </div>
      ) : (
        <ul role="list" className="space-y-2">
          {datasets.map(ds => {
            const cols = colsById[ds.id]
            const selected = selectedDatasetIds.includes(ds.id)
            return (
              <li
                key={ds.id}
                className={`rounded-md border px-3 py-2 ${
                  selected ? 'border-blue-300 bg-blue-50' : 'border-gray-200'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex min-w-0 flex-1 items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => onToggleSelect(ds.id)}
                      aria-label={`Include ${ds.filename} in the next question`}
                      className="h-4 w-4 shrink-0"
                    />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-800">
                      {ds.filename}
                    </span>
                  </label>

                  <span className="shrink-0 text-xs tabular-nums text-gray-500">
                    {ds.row_count} × {ds.col_count}
                  </span>
                  <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">
                    {ds.format}
                  </span>

                  <button
                    type="button"
                    onClick={() => void toggleCols(ds.id)}
                    aria-expanded={cols ? true : false}
                    aria-label={`Toggle columns for ${ds.filename}`}
                    className="shrink-0 rounded border border-gray-200 bg-white px-2 py-0.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    cols
                  </button>

                  {confirmingId === ds.id ? (
                    <span className="flex shrink-0 items-center gap-1">
                      <span className="text-xs text-gray-600">Delete?</span>
                      <button
                        type="button"
                        onClick={() => void confirmDelete(ds.id)}
                        disabled={deletingId === ds.id}
                        className="rounded border border-red-300 bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
                      >
                        {deletingId === ds.id ? 'Deleting…' : 'Yes'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmingId(null)}
                        className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                      >
                        No
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmingId(ds.id)}
                      aria-label={`Delete ${ds.filename}`}
                      className="shrink-0 rounded border border-gray-200 bg-white px-2 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  )}
                </div>

                {/* Columns disclosure */}
                {cols && (
                  <div className="mt-2 border-t border-gray-100 pt-2">
                    {cols.loading ? (
                      <p className="text-xs text-gray-400">Loading columns…</p>
                    ) : cols.error ? (
                      <p role="alert" className="text-xs text-red-600">
                        {cols.error}
                      </p>
                    ) : cols.columns && cols.columns.length > 0 ? (
                      <ul className="flex flex-wrap gap-1.5">
                        {cols.columns.map(c => (
                          <li
                            key={c.name}
                            className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-700"
                          >
                            <span className="font-medium">{c.name}</span>
                            <span className="text-gray-400"> · {c.dtype}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-gray-400">No columns reported.</p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
