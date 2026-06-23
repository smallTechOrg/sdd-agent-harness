'use client'

import { useState } from 'react'
import { AUDIT_EXPORT_URL, type AuditEntry } from '../lib/api'

interface AuditLogProps {
  entries: AuditEntry[]
  loading: boolean
}

function StatusBadge({ status }: { status: string }) {
  const ok = status === 'completed'
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
        ok ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      {status}
    </span>
  )
}

function SqlCell({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false)
  const truncated = sql.length > 60
  if (!truncated) {
    return <code className="font-mono text-xs text-gray-600">{sql}</code>
  }
  return (
    <button
      type="button"
      onClick={() => setOpen(o => !o)}
      aria-expanded={open}
      className="text-left font-mono text-xs text-gray-600 hover:text-gray-900 focus:outline-none"
      title="Click to expand"
    >
      {open ? sql : `${sql.slice(0, 60)}…`}
    </button>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export default function AuditLog({ entries, loading }: AuditLogProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Audit Log</h2>
        <a
          href={AUDIT_EXPORT_URL}
          download
          className="inline-flex items-center rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Export CSV
        </a>
      </div>

      {loading ? (
        <div className="space-y-2" aria-busy="true">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="h-8 animate-pulse rounded bg-gray-100 motion-reduce:animate-none"
            />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <p className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-sm text-gray-500">
          No operations logged yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-600">
                  Time
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-600">
                  Question
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-600">
                  SQL
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-600">
                  Rows
                </th>
                <th scope="col" className="px-3 py-2 text-right font-semibold text-gray-600">
                  Duration
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold text-gray-600">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {entries.map(entry => (
                <tr key={entry.id} className="align-top hover:bg-gray-50">
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-gray-500">
                    {formatTime(entry.created_at)}
                  </td>
                  <td className="px-3 py-2 text-gray-800">{entry.nl_question}</td>
                  <td className="px-3 py-2">
                    <SqlCell sql={entry.generated_sql ?? ''} />
                  </td>
                  <td className="px-3 py-2 text-right text-gray-700">
                    {entry.row_count ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-700">
                    {entry.duration_ms != null ? `${entry.duration_ms} ms` : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={entry.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
