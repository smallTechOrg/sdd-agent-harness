import { ComingSoonPill } from './ComingSoon'

// Renders columns as headers and rows as the body.
// Empty rows (no error) show a neutral message rather than an empty grid.
export function ResultTable({
  columns,
  rows,
}: {
  columns: string[]
  rows: unknown[][]
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-gray-700">Result table</h2>
        <span className="text-xs text-gray-400">Drill-down</span>
        <ComingSoonPill />
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
          No rows matched your question.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                {columns.map(col => (
                  <th
                    key={col}
                    className="px-4 py-2 text-left font-semibold text-gray-700"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((row, ri) => (
                <tr key={ri} className="hover:bg-gray-50">
                  {columns.map((_, ci) => (
                    <td key={ci} className="px-4 py-2 text-gray-800">
                      {formatCell(row[ci])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
