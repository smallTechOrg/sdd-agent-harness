'use client'

import { useState } from 'react'
import type { AskResult } from '../lib/api'

interface ResultViewProps {
  result: AskResult | null
}

function formatCell(value: string | number | null): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString()
  return String(value)
}

export default function ResultView({ result }: ResultViewProps) {
  const [showSql, setShowSql] = useState(false)

  if (!result) {
    return (
      <p className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6 text-center text-sm text-gray-500">
        Ask a question to see results.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-base leading-relaxed text-gray-800">{result.narrative}</p>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {result.columns.map(col => (
                <th
                  key={col}
                  className="px-3 py-2 text-left font-semibold text-gray-600"
                  scope="col"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {result.rows.length === 0 ? (
              <tr>
                <td
                  colSpan={Math.max(result.columns.length, 1)}
                  className="px-3 py-4 text-center text-gray-400"
                >
                  No rows returned.
                </td>
              </tr>
            ) : (
              result.rows.map((row, ri) => (
                <tr key={ri} className="hover:bg-gray-50">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 text-gray-700">
                      {formatCell(cell)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-500">
        {result.row_count.toLocaleString()} {result.row_count === 1 ? 'row' : 'rows'} ·{' '}
        {result.duration_ms} ms
      </p>

      <div>
        <button
          type="button"
          onClick={() => setShowSql(s => !s)}
          aria-expanded={showSql}
          className="text-sm text-blue-600 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {showSql ? 'Hide SQL' : 'Show SQL'}
        </button>
        {showSql && (
          <pre className="mt-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100">
            <code>{result.sql}</code>
          </pre>
        )}
      </div>
    </div>
  )
}
