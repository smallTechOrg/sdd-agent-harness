'use client'

import type { SummaryTable as SummaryTableData } from '../lib/types'

interface SummaryTableProps {
  table: SummaryTableData
}

function fmtCell(v: string | number | null): string {
  if (v == null) return '—'
  if (typeof v === 'number') {
    return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, {
      maximumFractionDigits: 4,
    })
  }
  return String(v)
}

export function SummaryTable({ table }: SummaryTableProps) {
  const { columns, rows } = table
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-sm" data-testid="summary-table">
        <thead className="bg-slate-50">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            {columns.map((c, i) => (
              <th key={i} className="px-4 py-2 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, ri) => (
            <tr key={ri} className="text-slate-700">
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className={`px-4 py-2 ${typeof cell === 'number' ? 'text-right font-mono tabular-nums' : ''}`}
                >
                  {fmtCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="px-4 py-3 text-sm text-slate-500">
          The result had no rows.
        </p>
      )}
    </div>
  )
}
