'use client'

import { useState } from 'react'
import {
  getMessage,
  normalizeResultTable,
  formatCost,
  ApiError,
  NetworkError,
  type HistoryItem,
  type MessageDetail,
} from '@/lib/api'
import KeyNumbers from './KeyNumbers'
import ResultTable from './ResultTable'
import CodePanel from './CodePanel'

interface HistoryBrowserProps {
  history: HistoryItem[]
}

function statusPill(status: string) {
  const failed = status === 'failed'
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
        failed ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700'
      }`}
    >
      {status}
    </span>
  )
}

function timeLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Run-history list. Each row expands to fetch and show the full plan, code,
 * result, key numbers, tokens, and cost (GET /api/messages/{id}).
 */
export default function HistoryBrowser({ history }: HistoryBrowserProps) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [details, setDetails] = useState<Record<string, MessageDetail>>({})
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [errorId, setErrorId] = useState<{ id: string; message: string } | null>(null)

  async function toggle(id: string) {
    if (openId === id) {
      setOpenId(null)
      return
    }
    setOpenId(id)
    setErrorId(null)
    if (!details[id]) {
      setLoadingId(id)
      try {
        const detail = await getMessage(id)
        setDetails((prev) => ({ ...prev, [id]: detail }))
      } catch (err) {
        const message =
          err instanceof ApiError || err instanceof NetworkError
            ? err.message
            : 'Could not load this run.'
        setErrorId({ id, message })
      } finally {
        setLoadingId(null)
      }
    }
  }

  if (history.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-gray-200 px-3 py-4 text-center text-xs text-gray-400">
        No runs yet. Ask a question to start the audit trail.
      </p>
    )
  }

  return (
    <div className="space-y-1.5">
      {history.map((item) => {
        const open = openId === item.id
        const detail = details[item.id]
        return (
          <div key={item.id} className="overflow-hidden rounded-md border border-gray-200">
            <button
              type="button"
              onClick={() => void toggle(item.id)}
              className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-gray-50"
              aria-expanded={open}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-gray-800" title={item.question}>
                  {item.question}
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-400">
                  {statusPill(item.status)}
                  <span>{formatCost(item.cost_usd)}</span>
                  <span>· {timeLabel(item.created_at)}</span>
                </div>
              </div>
              <svg
                className={`mt-1 h-3 w-3 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </button>

            {open && (
              <div className="border-t border-gray-100 bg-gray-50 px-3 py-2.5">
                {loadingId === item.id && (
                  <p className="text-xs text-gray-400">Loading run detail…</p>
                )}
                {errorId?.id === item.id && (
                  <p className="text-xs text-red-600" role="alert">
                    {errorId.message}
                  </p>
                )}
                {detail && <RunDetail detail={detail} />}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function RunDetail({ detail }: { detail: MessageDetail }) {
  const table = normalizeResultTable(detail.result_table)
  return (
    <div className="space-y-3">
      {detail.plan && (
        <Section title="Plan">
          <pre className="whitespace-pre-wrap text-xs leading-relaxed text-gray-600">
            {detail.plan}
          </pre>
        </Section>
      )}

      {detail.status === 'failed' && detail.error && (
        <Section title="Error">
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-red-700">
            {detail.error}
          </pre>
        </Section>
      )}

      {detail.answer && (
        <Section title="Answer">
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-700">
            {detail.answer}
          </p>
        </Section>
      )}

      {detail.key_numbers && Object.keys(detail.key_numbers).length > 0 && (
        <Section title="Key numbers">
          <KeyNumbers numbers={detail.key_numbers} />
        </Section>
      )}

      {table && (
        <Section title="Result">
          <ResultTable table={table} />
        </Section>
      )}

      {detail.generated_code && (
        <Section title="Code">
          <CodePanel code={detail.generated_code} defaultOpen />
        </Section>
      )}

      <div className="flex flex-wrap gap-x-3 text-[11px] text-gray-400">
        {detail.prompt_tokens != null && <span>{detail.prompt_tokens.toLocaleString()} prompt</span>}
        {detail.completion_tokens != null && (
          <span>{detail.completion_tokens.toLocaleString()} completion</span>
        )}
        <span>· {formatCost(detail.cost_usd)}</span>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
        {title}
      </div>
      {children}
    </div>
  )
}
