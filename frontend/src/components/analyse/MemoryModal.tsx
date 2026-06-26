'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type MemoryResponse } from '@/lib/api'

/**
 * Project notes / global-memory modal (Phase 3 — C29/C31).
 *
 * Reachable from the Analyse sidebar's "Project notes" button. On open it loads
 * GET /memory, lets the user edit the free-text `global_memory`, and saves via
 * PATCH /memory (which triggers C31 compression server-side). The response's
 * compressed `global_memory_facts` are shown read-only so the user sees what the
 * agent will treat as authoritative on every plan_action.
 *
 * Covers all four states: loading, error (with retry), saving, and the ideal
 * edit view. Backdrop + Escape close; focus moves to the textarea on open.
 */
export function MemoryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [facts, setFacts] = useState<string[]>([])
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const applyMemory = useCallback((m: MemoryResponse) => {
    setText(m.global_memory ?? '')
    setFacts(Array.isArray(m.global_memory_facts) ? m.global_memory_facts : [])
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      applyMemory(await api.getMemory())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project notes.')
    } finally {
      setLoading(false)
    }
  }, [applyMemory])

  // Load fresh memory each time the modal opens.
  useEffect(() => {
    if (open) {
      setSaveError(null)
      setSavedAt(null)
      void load()
    }
  }, [open, load])

  // Focus the textarea once content is ready.
  useEffect(() => {
    if (open && !loading && !error) {
      textareaRef.current?.focus()
    }
  }, [open, loading, error])

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const save = useCallback(async () => {
    setSaving(true)
    setSaveError(null)
    try {
      applyMemory(await api.patchMemory(text))
      setSavedAt(Date.now())
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save project notes.')
    } finally {
      setSaving(false)
    }
  }, [text, applyMemory])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={e => {
        // Backdrop click (not a click that started inside the dialog) closes.
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-modal-title"
        className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-lg bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 id="memory-modal-title" className="text-sm font-semibold text-gray-800">
            Project notes (global memory)
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close project notes"
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4">
          <p className="mb-3 text-xs text-gray-500">
            Notes the agent treats as authoritative on every question (e.g. how to
            interpret a column, business rules). Saving compresses them into the
            fact list below.
          </p>

          {loading ? (
            <p className="py-8 text-center text-xs text-gray-400">Loading project notes…</p>
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
          ) : (
            <>
              <label htmlFor="memory-textarea" className="sr-only">
                Project notes
              </label>
              <textarea
                id="memory-textarea"
                ref={textareaRef}
                rows={6}
                value={text}
                onChange={e => setText(e.target.value)}
                placeholder="e.g. The `amount` column is in USD. Treat status='X' as cancelled."
                className="w-full resize-y rounded-md border border-gray-200 p-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />

              {saveError && (
                <p role="alert" className="mt-2 text-xs text-red-600">
                  {saveError}
                </p>
              )}

              <div className="mt-4">
                <p className="mb-1.5 text-[11px] font-medium text-gray-500">
                  Compressed facts (read-only)
                </p>
                {facts.length === 0 ? (
                  <p className="rounded-md border border-dashed border-gray-200 px-3 py-3 text-center text-xs text-gray-400">
                    No facts yet — write some notes and save.
                  </p>
                ) : (
                  <ul role="list" className="space-y-1.5">
                    {facts.map((f, i) => (
                      <li
                        key={i}
                        className="rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs text-gray-700"
                      >
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-gray-200 px-4 py-3">
          <span className="text-[11px] text-gray-400" aria-live="polite">
            {savedAt ? 'Saved.' : ''}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Close
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={loading || !!error || saving}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-500"
            >
              {saving && (
                <span
                  aria-hidden="true"
                  className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
                />
              )}
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
