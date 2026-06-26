'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, type Session } from '@/lib/api'

/**
 * Sessions sidebar (C9) — REAL in Phase 3.
 *
 * Lists sessions from GET /sessions (most-recently-updated first), each showing
 * its name (or `first_question` as a fallback label) and turn count. Supports:
 *  - **+New**  — clears the active conversation; the next /ask with no
 *    session_id creates the session server-side (the parent adopts the returned
 *    session_id and refreshes the list).
 *  - **Resume** — click a session → the parent loads GET /sessions/{id}.
 *  - **Rename** — inline edit → PATCH /sessions/{id}/name → refresh.
 *  - **Delete** — per-session → DELETE /sessions/{id} → refresh (the parent
 *    clears the conversation if the active session was deleted).
 *  - **Clear all** — DELETE /sessions behind a confirm → refresh.
 *  - **Project notes** — opens the global-memory modal.
 *
 * The list refreshes whenever `refreshToken` changes (the parent bumps it after
 * each completed ask so turn counts / ordering update). All states (loading,
 * error, empty, list) render explicitly so a failure never blanks the panel.
 */
export function SessionSidebar({
  activeSessionId,
  refreshToken,
  onResume,
  onNew,
  onSessionDeleted,
  onAllDeleted,
  onOpenMemory,
}: {
  activeSessionId: string | null
  refreshToken: number
  onResume: (id: string) => void
  onNew: () => void
  onSessionDeleted: (id: string) => void
  onAllDeleted: () => void
  onOpenMemory: () => void
}) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const [clearingAll, setClearingAll] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const list = await api.listSessions()
      setSessions(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refreshToken])

  const startRename = useCallback((s: Session) => {
    setRenamingId(s.id)
    setRenameValue(s.name ?? s.first_question ?? '')
  }, [])

  const commitRename = useCallback(
    async (id: string) => {
      const name = renameValue.trim()
      if (!name) {
        setRenamingId(null)
        return
      }
      setBusyId(id)
      try {
        await api.renameSession(id, name)
        setRenamingId(null)
        await load()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to rename session.')
      } finally {
        setBusyId(null)
      }
    },
    [renameValue, load],
  )

  const doDelete = useCallback(
    async (id: string) => {
      setBusyId(id)
      try {
        await api.deleteSession(id)
        setConfirmingId(null)
        setSessions(prev => prev.filter(s => s.id !== id))
        onSessionDeleted(id)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete session.')
      } finally {
        setBusyId(null)
      }
    },
    [onSessionDeleted],
  )

  const doClearAll = useCallback(async () => {
    setClearingAll(true)
    try {
      await api.deleteAllSessions()
      setConfirmClearAll(false)
      setSessions([])
      onAllDeleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear sessions.')
    } finally {
      setClearingAll(false)
    }
  }, [onAllDeleted])

  return (
    <section
      aria-labelledby="sessions-heading"
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="sessions-heading" className="text-sm font-semibold text-gray-800">
          Sessions
        </h2>
        <button
          type="button"
          onClick={onOpenMemory}
          className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
        >
          Project notes
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onNew}
          className="rounded-md border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
        >
          + New
        </button>
        {sessions.length > 0 &&
          (confirmClearAll ? (
            <span className="inline-flex items-center gap-1">
              <span className="text-xs text-gray-600">Clear all?</span>
              <button
                type="button"
                onClick={() => void doClearAll()}
                disabled={clearingAll}
                className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
              >
                {clearingAll ? 'Clearing…' : 'Yes'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmClearAll(false)}
                className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
              >
                No
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmClearAll(true)}
              className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
            >
              Clear all
            </button>
          ))}
      </div>

      {loading && sessions.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 px-3 py-6 text-center text-xs text-gray-400">
          Loading sessions…
        </div>
      ) : error ? (
        <div
          role="alert"
          className="flex flex-col items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-5 text-center text-xs text-red-700"
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
      ) : sessions.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 px-3 py-6 text-center text-xs text-gray-400">
          No sessions yet. Ask a question to start one.
        </div>
      ) : (
        <ul role="list" className="space-y-2">
          {sessions.map(s => {
            const active = activeSessionId === s.id
            const label = s.name?.trim() || s.first_question?.trim() || 'Untitled session'
            return (
              <li
                key={s.id}
                className={`rounded-md border px-2.5 py-2 ${
                  active ? 'border-blue-300 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                {renamingId === s.id ? (
                  <div className="flex items-center gap-1.5">
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={e => setRenameValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') void commitRename(s.id)
                        if (e.key === 'Escape') setRenamingId(null)
                      }}
                      aria-label={`Rename session ${label}`}
                      className="min-w-0 flex-1 rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
                    />
                    <button
                      type="button"
                      onClick={() => void commitRename(s.id)}
                      disabled={busyId === s.id}
                      className="rounded border border-blue-300 bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setRenamingId(null)}
                      className="rounded border border-gray-300 bg-white px-2 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div>
                    <button
                      type="button"
                      onClick={() => onResume(s.id)}
                      className="block w-full text-left"
                    >
                      <span className="block truncate text-sm font-medium text-gray-800">
                        {label}
                      </span>
                      <span className="text-[11px] text-gray-500">
                        {s.turn_count} turn{s.turn_count === 1 ? '' : 's'}
                        {active ? ' · active' : ''}
                      </span>
                    </button>

                    <div className="mt-1.5 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => startRename(s)}
                        className="text-[11px] font-medium text-gray-500 hover:text-gray-800"
                      >
                        Rename
                      </button>
                      {confirmingId === s.id ? (
                        <span className="inline-flex items-center gap-1">
                          <span className="text-[11px] text-gray-600">Delete?</span>
                          <button
                            type="button"
                            onClick={() => void doDelete(s.id)}
                            disabled={busyId === s.id}
                            className="text-[11px] font-medium text-red-600 hover:text-red-800 disabled:opacity-60"
                          >
                            {busyId === s.id ? 'Deleting…' : 'Yes'}
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmingId(null)}
                            className="text-[11px] font-medium text-gray-500 hover:text-gray-800"
                          >
                            No
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmingId(s.id)}
                          className="text-[11px] font-medium text-red-600 hover:text-red-800"
                        >
                          Delete
                        </button>
                      )}
                    </div>
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
