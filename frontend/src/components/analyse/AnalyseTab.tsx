'use client'

import { useCallback, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { SessionSidebar } from '@/components/analyse/SessionSidebar'
import { TokenWidget } from '@/components/analyse/TokenWidget'
import { TablesCard } from '@/components/analyse/TablesCard'
import { UploadCard } from '@/components/analyse/UploadCard'
import {
  ConversationCard,
  type ConversationHandle,
} from '@/components/analyse/ConversationCard'

/** Token counts from the most recent completed ask (drives the TokenWidget). */
export interface LastQueryTokens {
  input: number
  output: number
}

/**
 * Analyse tab — the real Phase-3 surface.
 *
 * Owns the shared state the cards coordinate on:
 *  - `selectedDatasetIds` : the explicit multi-dataset selection (empty → the
 *    server's C19 selector picks). The Tables card's checkboxes set it.
 *  - `sessionId`          : the active conversation session. New is created
 *    server-side on the next /ask with no session_id; the answer's session_id is
 *    adopted here. Resuming a session loads its turns into the conversation card.
 *  - `datasetsVersion`    : a bump token telling the Tables card to re-fetch.
 *  - `sessionsVersion`    : a bump token telling the sidebar to re-fetch (after
 *    each ask, so turn counts / ordering update).
 *  - `lastTokens`         : in/out tokens from the latest answer (Token widget).
 *
 * The global-memory ("Project notes") modal is hoisted to AppShell so the header
 * button and the sidebar button open the same modal; `onOpenMemory` opens it.
 *
 * Layout: a left sidebar (sessions + token usage) and a main column (tables,
 * upload, conversation). Stacks on narrow viewports.
 */
export function AnalyseTab({
  provider,
  onOpenMemory,
}: {
  provider?: string
  onOpenMemory: () => void
}) {
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<string[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [datasetsVersion, setDatasetsVersion] = useState(0)
  const [sessionsVersion, setSessionsVersion] = useState(0)
  const [lastTokens, setLastTokens] = useState<LastQueryTokens | null>(null)

  const conversationRef = useRef<ConversationHandle>(null)

  const refreshDatasets = useCallback(() => setDatasetsVersion(v => v + 1), [])
  const refreshSessions = useCallback(() => setSessionsVersion(v => v + 1), [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedDatasetIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )
  }, [])

  const clearSelection = useCallback(() => setSelectedDatasetIds([]), [])

  // When a dataset is deleted, drop it from the selection.
  const handleDatasetDeleted = useCallback(
    (deletedId: string) => {
      setSelectedDatasetIds(prev => prev.filter(x => x !== deletedId))
      refreshDatasets()
    },
    [refreshDatasets],
  )

  // --- Session lifecycle ----------------------------------------------------

  // +New: clear the active conversation; the next ask starts a fresh session.
  const handleNewSession = useCallback(() => {
    setSessionId(null)
    conversationRef.current?.reset()
  }, [])

  // Resume: load the session detail and hydrate the conversation thread.
  const handleResume = useCallback(async (id: string) => {
    try {
      const detail = await api.getSession(id)
      setSessionId(detail.id)
      conversationRef.current?.hydrate(detail)
    } catch {
      // A failed resume leaves the current thread untouched; the sidebar will
      // surface the error on its own next refresh. Reset to a clean state so the
      // user isn't stuck on a half-loaded session.
      setSessionId(id)
      conversationRef.current?.reset()
    }
  }, [])

  // The conversation card adopts the server-assigned session id after an ask.
  const handleSessionStarted = useCallback(
    (id: string) => {
      setSessionId(prev => (prev === id ? prev : id))
      // New/continued session → refresh the sidebar so it appears / updates.
      refreshSessions()
    },
    [refreshSessions],
  )

  const handleSessionDeleted = useCallback(
    (id: string) => {
      if (sessionId === id) {
        setSessionId(null)
        conversationRef.current?.reset()
      }
    },
    [sessionId],
  )

  const handleAllSessionsDeleted = useCallback(() => {
    setSessionId(null)
    conversationRef.current?.reset()
  }, [])

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
      {/* Sidebar */}
      <aside className="flex flex-col gap-4">
        <SessionSidebar
          activeSessionId={sessionId}
          refreshToken={sessionsVersion}
          onResume={id => void handleResume(id)}
          onNew={handleNewSession}
          onSessionDeleted={handleSessionDeleted}
          onAllDeleted={handleAllSessionsDeleted}
          onOpenMemory={onOpenMemory}
        />
        <TokenWidget provider={provider} lastTokens={lastTokens} />
      </aside>

      {/* Main column */}
      <div className="flex flex-col gap-4">
        <TablesCard
          datasetsVersion={datasetsVersion}
          selectedDatasetIds={selectedDatasetIds}
          onToggleSelect={toggleSelect}
          onClearSelection={clearSelection}
          onDeleted={handleDatasetDeleted}
        />
        <UploadCard onUploaded={refreshDatasets} />
        <ConversationCard
          handleRef={conversationRef}
          selectedDatasetIds={selectedDatasetIds}
          sessionId={sessionId}
          onSessionStarted={handleSessionStarted}
          onAnswered={tokens => {
            setLastTokens(tokens)
            refreshDatasets()
            refreshSessions()
          }}
        />
      </div>
    </div>
  )
}
