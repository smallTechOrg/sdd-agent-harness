'use client'

import { type ResultTable as ResultTableData } from '@/lib/api'

interface ResultTableProps {
  table: ResultTableData
}

function renderCell(v: string | number | boolean | null): string {
  if (v == null) return '—'
  if (typeof v === 'number') {
    // Trim noisy float tails but keep precision for small magnitudes.
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
  return String(v)
}

/** Renders a normalized summary table. Caps rows for very large results. */
export default function ResultTable({ table }: ResultTableProps) {
  const MAX_ROWS = 50
  const rows = table.rows.slice(0, MAX_ROWS)
  const truncated = table.rows.length > MAX_ROWS
  if (table.columns.length === 0 || rows.length === 0) return null

  return (
    <div className="overflow-hidden rounded-md border border-gray-200">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-600">
              {table.columns.map((c, i) => (
                <th key={i} className="whitespace-nowrap border-b border-gray-200 px-3 py-2 font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className="even:bg-gray-50/50">
                {row.map((cell, ci) => (
                  <td key={ci} className="whitespace-nowrap border-b border-gray-100 px-3 py-1.5 text-gray-800">
                    {renderCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="border-t border-gray-100 bg-gray-50 px-3 py-1.5 text-[11px] text-gray-400">
          Showing first {MAX_ROWS} of {table.rows.length.toLocaleString()} rows.
        </div>
      )}
    </div>
  )
}
