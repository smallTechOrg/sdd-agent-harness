'use client'

interface TableInfo {
  table_name: string
  row_count: number
  filename: string
  columns?: string[]
}

interface TablePillsProps {
  tables: TableInfo[]
}

const MAX_VISIBLE = 10

export default function TablePills({ tables }: TablePillsProps) {
  if (tables.length === 0) {
    return (
      <p className="text-xs italic text-gray-400">No files uploaded yet</p>
    )
  }

  const visible = tables.slice(0, MAX_VISIBLE)
  const overflow = tables.length - MAX_VISIBLE

  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((t) => (
        <div
          key={t.table_name}
          title={t.columns?.length ? `Columns: ${t.columns.join(', ')}` : t.filename}
          className="group relative cursor-default rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700 border border-indigo-200"
        >
          <span className="font-semibold">{t.table_name}</span>
          <span className="ml-1 text-indigo-400">{t.row_count.toLocaleString()} rows</span>
        </div>
      ))}
      {overflow > 0 && (
        <div className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500">
          +{overflow} more
        </div>
      )}
    </div>
  )
}
