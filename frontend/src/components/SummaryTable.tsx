'use client'

import type { SummaryTable as SummaryTableType } from '@/lib/api'

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString()
  return String(value)
}

/**
 * The RICH summary table (Phase 2) — rendered from the backend `summary_table`
 * spec: typed columns with right-aligned numerics and headers from `columns`.
 * Distinct from the basic Phase-1 result table; shown when present.
 */
export function SummaryTable({ table }: { table: SummaryTableType }) {
  const columns = table.columns ?? []
  const rows = table.rows ?? []
  if (!columns.length || !rows.length) return null

  return (
    <div>
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Summary
      </div>
      <div
        className="overflow-x-auto rounded-lg border border-gray-200"
        data-testid="summary-table"
      >
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((c, i) => (
                <th
                  key={`${c.name}-${i}`}
                  className={`px-3 py-2 font-medium text-gray-600 ${
                    c.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100" data-testid="summary-table-body">
            {rows.map((row, ri) => (
              <tr key={ri}>
                {columns.map((c, ci) => (
                  <td
                    key={ci}
                    className={`px-3 py-2 text-gray-800 ${
                      c.align === 'right' ? 'text-right font-mono' : 'text-left'
                    }`}
                  >
                    {formatCell(row?.[ci])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
