'use client'

import { useState, useEffect, useRef } from 'react'
import FileDropZone from '../components/FileDropZone'
import TablePills from '../components/TablePills'
import ChatThread, { type Message } from '../components/ChatThread'
import MessageInput from '../components/MessageInput'
import type { ChartSpec } from '../components/ChartPanel'

interface UploadedTableInfo {
  table_name: string
  row_count: number
  filename: string
  columns: string[]
}

const SESSION_STORAGE_KEY = 'data_agent_session_id'

let msgCounter = 0
function nextId(): string {
  return `msg-${++msgCounter}-${Date.now()}`
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [tables, setTables] = useState<UploadedTableInfo[]>([])
  const [analyzing, setAnalyzing] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  // On mount: restore or create a session
  useEffect(() => {
    const init = async () => {
      const stored = typeof window !== 'undefined'
        ? localStorage.getItem(SESSION_STORAGE_KEY)
        : null

      if (stored) {
        // Try to reuse the stored session by fetching its files
        try {
          const res = await fetch(`/sessions/${stored}/files`)
          const json = await res.json()
          if (res.ok && json.data) {
            setSessionId(stored)
            const files: UploadedTableInfo[] = (json.data?.files ?? []).map(
              (f: { table_name: string; row_count: number; filename: string; columns: string[] }) => ({
                table_name: f.table_name,
                row_count: f.row_count,
                filename: f.filename,
                columns: f.columns ?? [],
              })
            )
            setTables(files)
            return
          }
        } catch {
          // fall through to create new session
        }
      }

      // Create a new session
      try {
        const res = await fetch('/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
        const json = await res.json()
        if (res.ok && json.data) {
          const id: string = json.data.session_id
          setSessionId(id)
          if (typeof window !== 'undefined') {
            localStorage.setItem(SESSION_STORAGE_KEY, id)
          }
        } else {
          setSessionError('Could not start a session. Is the server running?')
        }
      } catch {
        setSessionError('Network error — is the server running?')
      }
    }

    init()
  }, [])

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleFileUploaded = (info: UploadedTableInfo) => {
    setTables((prev) => {
      // avoid duplicate entries for same table_name
      const others = prev.filter((t) => t.table_name !== info.table_name)
      return [...others, info]
    })
  }

  const handleAnalyze = async (question: string) => {
    if (!sessionId) return
    setAnalyzing(true)

    const userMsgId = nextId()
    const agentMsgId = nextId()

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', content: question },
      { id: agentMsgId, role: 'agent', agentData: { isLoading: true } },
    ])

    try {
      const res = await fetch(`/sessions/${sessionId}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const json = await res.json()

      if (!res.ok || !json.data) {
        const errMsg = json?.error?.message ?? `Analysis failed (${res.status})`
        setMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId
              ? { ...m, agentData: { error: errMsg, isLoading: false } }
              : m
          )
        )
      } else {
        const d = json.data
        setMessages((prev) =>
          prev.map((m) =>
            m.id === agentMsgId
              ? {
                  ...m,
                  agentData: {
                    runId: d.run_id,
                    sqlQuery: d.sql_query,
                    outputText: d.output_text,
                    insightJson: d.insight_json,
                    chartSpecs: (d.chart_specs ?? []) as ChartSpec[],
                    isLoading: false,
                  },
                }
              : m
          )
        )
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === agentMsgId
            ? { ...m, agentData: { error: 'Network error — is the server running?', isLoading: false } }
            : m
        )
      )
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left sidebar */}
      <aside className="flex w-72 flex-col border-r border-gray-200 bg-gray-50">
        <div className="flex flex-col gap-5 p-4 flex-1">
          <h1 className="text-lg font-bold tracking-tight text-gray-900">Data Analysis Agent</h1>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Upload data</p>
            {sessionId ? (
              <FileDropZone
                sessionId={sessionId}
                onFileUploaded={handleFileUploaded}
                disabled={analyzing}
              />
            ) : (
              <div className="flex h-28 items-center justify-center rounded-xl border-2 border-dashed border-gray-200">
                {sessionError ? (
                  <p className="px-3 text-center text-xs text-red-500">{sessionError}</p>
                ) : (
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                    </svg>
                    Starting session…
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Uploaded tables</p>
            <TablePills tables={tables} />
          </div>
        </div>

        {/* Phase 2 stub — PostgreSQL connection */}
        <div className="mt-auto border-t border-gray-200 p-3 opacity-40 pointer-events-none select-none">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">PostgreSQL</p>
          <p className="text-xs italic text-gray-400">Coming in Phase 2</p>
        </div>
      </aside>

      {/* Right main area */}
      <div className="flex flex-1 flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3">
          <p className="text-sm font-medium text-gray-700">Data Analysis Agent</p>
          <button
            disabled
            title="Coming Later"
            className="cursor-not-allowed rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-400 opacity-40"
          >
            Export (Coming Later)
          </button>
        </header>

        {/* Chat area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <ChatThread messages={messages} />
          <div ref={chatBottomRef} />
        </div>

        {/* Input */}
        <MessageInput
          onSubmit={handleAnalyze}
          disabled={!sessionId || tables.length === 0 || analyzing}
          placeholder={
            !sessionId
              ? 'Starting session…'
              : tables.length === 0
              ? 'Upload a file to start asking questions'
              : 'Ask a question about your data…'
          }
        />
      </div>
    </div>
  )
}
