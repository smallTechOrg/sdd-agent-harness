'use client'

import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  NetworkError,
  type DatasetProfile,
  type ThreadMessage,
} from '@/lib/api'
import { streamAnalysis } from '@/lib/sse'
import AnswerTurn, { type TurnData } from './AnswerTurn'

interface ChatPanelProps {
  datasetId: string
  profile: DatasetProfile
  /** Prior turns rehydrated from GET /api/datasets/{id}. */
  initialMessages: ThreadMessage[]
  /** Called after a run completes/fails so the history panel can refresh. */
  onRunComplete?: () => void
}

function messageToTurn(m: ThreadMessage): TurnData {
  const status: TurnData['status'] = m.status === 'failed' ? 'failed' : 'completed'
  return {
    id: m.id,
    question: m.question,
    answer: m.answer ?? '',
    code: '',
    plan: '',
    keyNumbers: m.key_numbers ?? null,
    resultTable: m.result_table ?? null,
    promptTokens: null,
    completionTokens: null,
    costUsd: m.cost_usd ?? null,
    status,
    step: null,
    error: status === 'failed' ? (m.answer ?? 'This run failed.') : null,
    errorCode: null,
  }
}

/**
 * Reconcile the rehydrated thread (GET /api/datasets/{id}) with the turns the
 * client already holds, MERGING by message id.
 *
 * The dataset-thread contract intentionally omits `generated_code` and the
 * prompt/completion token split (those live in GET /api/messages/{id}). So a
 * naive replace would wipe the "Show code" panel + token spans off a turn the
 * client just answered live — they came from the SSE `code`/`done` events and
 * are only held in memory. This merge preserves those richer in-memory fields
 * whenever the rehydrated entry is leaner, and never downgrades a non-empty
 * `code` to `''` or non-null tokens to `null`.
 *
 * New messages (ids the client has never seen) map normally, so a genuine page
 * reload still rehydrates prior turns from the DB.
 */
function mergeThread(prev: TurnData[], rehydrated: ThreadMessage[]): TurnData[] {
  const byId = new Map(prev.map((t) => [t.id, t]))
  return rehydrated.map((m) => {
    const fresh = messageToTurn(m)
    const existing = byId.get(m.id)
    if (!existing) return fresh
    return {
      ...fresh,
      // Preserve richer fields the rehydrated lean thread lacks.
      code: fresh.code || existing.code,
      plan: fresh.plan || existing.plan,
      promptTokens: fresh.promptTokens ?? existing.promptTokens,
      completionTokens: fresh.completionTokens ?? existing.completionTokens,
      // Prefer richer values from either source for these display fields.
      answer: fresh.answer || existing.answer,
      keyNumbers: fresh.keyNumbers ?? existing.keyNumbers,
      resultTable: fresh.resultTable ?? existing.resultTable,
      costUsd: fresh.costUsd ?? existing.costUsd,
      error: fresh.error ?? existing.error,
      errorCode: existing.errorCode ?? fresh.errorCode,
    }
  })
}

/** Build static starter-question chips from the profile column names. */
function buildStarters(profile: DatasetProfile): string[] {
  const starters: string[] = ['How many rows are in this dataset?']
  const numeric = profile.columns.find(
    (c) => c.mean != null || c.dtype.includes('float') || c.dtype.includes('int'),
  )
  const categorical = profile.columns.find(
    (c) => c.dtype === 'object' || c.dtype.includes('str') || c.dtype.includes('category'),
  )
  if (numeric) starters.push(`What's the average of ${numeric.name}?`)
  if (categorical) starters.push(`What are the distinct values of ${categorical.name}?`)
  if (numeric && categorical)
    starters.push(`What's the average ${numeric.name} by ${categorical.name}?`)
  return starters.slice(0, 4)
}

export default function ChatPanel({
  datasetId,
  profile,
  initialMessages,
  onRunComplete,
}: ChatPanelProps) {
  const [turns, setTurns] = useState<TurnData[]>(() => initialMessages.map(messageToTurn))
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const starters = buildStarters(profile)

  // Rehydrate when the thread changes — but MERGE by id so a just-answered live
  // turn keeps its in-memory `code` + token split (which the lean dataset-thread
  // contract omits) instead of being downgraded on the post-run refresh. A real
  // page reload still rehydrates prior turns, since unseen ids map normally.
  useEffect(() => {
    setTurns((prev) => mergeThread(prev, initialMessages))
  }, [initialMessages])

  // Auto-scroll to the newest turn.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  useEffect(() => {
    return () => abortRef.current?.abort()
  }, [])

  function patchLast(patch: Partial<TurnData>) {
    setTurns((prev) => {
      if (prev.length === 0) return prev
      const next = [...prev]
      next[next.length - 1] = { ...next[next.length - 1], ...patch }
      return next
    })
  }

  function appendToken(text: string) {
    setTurns((prev) => {
      if (prev.length === 0) return prev
      const next = [...prev]
      const last = next[next.length - 1]
      next[next.length - 1] = { ...last, answer: last.answer + text }
      return next
    })
  }

  async function submit(question: string) {
    const trimmed = question.trim()
    if (!trimmed || streaming) return
    setInput('')
    setStreaming(true)

    const tempId = `live-${Date.now()}`
    setTurns((prev) => [
      ...prev,
      {
        id: tempId,
        question: trimmed,
        answer: '',
        code: '',
        plan: '',
        keyNumbers: null,
        resultTable: null,
        promptTokens: null,
        completionTokens: null,
        costUsd: null,
        status: 'streaming',
        step: 'planning',
        error: null,
        errorCode: null,
      },
    ])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await streamAnalysis(
        datasetId,
        trimmed,
        {
          onStatus: (e) => patchLast({ step: e.step }),
          onPlan: (e) => patchLast({ plan: e.plan }),
          onCode: (e) => patchLast({ code: e.code }),
          onToken: (e) => appendToken(e.text),
          onDone: (e) =>
            patchLast({
              id: e.message_id || tempId,
              status: 'completed',
              step: null,
              keyNumbers: e.key_numbers ?? null,
              resultTable: e.result_table ?? null,
              promptTokens: e.prompt_tokens ?? null,
              completionTokens: e.completion_tokens ?? null,
              costUsd: e.cost_usd ?? null,
            }),
          onError: (e) =>
            patchLast({
              id: e.message_id || tempId,
              status: 'failed',
              step: null,
              error: e.error,
              errorCode: e.code ?? null,
            }),
        },
        controller.signal,
      )
    } catch (err) {
      // Transport-level failure (pre-stream 4xx or server down).
      const message =
        err instanceof ApiError || err instanceof NetworkError
          ? err.message
          : 'The request failed unexpectedly.'
      patchLast({ status: 'failed', step: null, error: message, errorCode: null })
    } finally {
      setStreaming(false)
      abortRef.current = null
      onRunComplete?.()
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    void submit(input)
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-gray-50">
      {/* Thread */}
      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <p className="text-sm font-medium text-gray-600">
              Ask a question about your data
            </p>
            <p className="mt-1 max-w-sm text-xs text-gray-400">
              The agent plans an analysis, writes pandas, runs it locally on the full
              file, and streams back a plain-English answer.
            </p>
          </div>
        ) : (
          turns.map((turn) => <AnswerTurn key={turn.id} turn={turn} />)
        )}
      </div>

      {/* Starter questions — REAL, seeded from the profile */}
      {!streaming && starters.length > 0 && (
        <div className="border-t border-gray-200 bg-white px-5 pt-3">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-400">
            Try asking
          </div>
          <div className="flex flex-wrap gap-2">
            {starters.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setInput(s)}
                className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={onSubmit} className="border-t border-gray-200 bg-white p-4">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void submit(input)
              }
            }}
            rows={1}
            placeholder="Ask a question about this dataset…"
            disabled={streaming}
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="shrink-0 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {streaming ? 'Working…' : 'Ask'}
          </button>
        </div>
      </form>
    </section>
  )
}
