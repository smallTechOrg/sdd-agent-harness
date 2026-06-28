'use client'

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ChartSpec, SummaryTable } from '../lib/types'

const COLORS = [
  '#6366f1',
  '#0ea5e9',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
]

interface ChartViewProps {
  spec: ChartSpec
  table: SummaryTable | null
}

// Build an array of row objects keyed by column name from the summary table.
function tableToRows(
  table: SummaryTable | null,
): Array<Record<string, string | number | null>> {
  if (!table || !table.columns || !table.rows) return []
  return table.rows.map((row) => {
    const obj: Record<string, string | number | null> = {}
    table.columns.forEach((col, i) => {
      obj[col] = row[i]
    })
    return obj
  })
}

function yKeys(spec: ChartSpec): string[] {
  if (Array.isArray(spec.y)) return spec.y
  if (spec.y) return [spec.y]
  return []
}

export function ChartView({ spec, table }: ChartViewProps) {
  const data = tableToRows(table)
  const xKey = spec.x ?? (table?.columns?.[0] ?? 'x')
  const ys = yKeys(spec)
  const yResolved =
    ys.length > 0 ? ys : table?.columns?.slice(1, 2) ?? []

  if (data.length === 0 || yResolved.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
        No chartable values for this result.
      </div>
    )
  }

  const type = (spec.type ?? 'bar').toLowerCase()

  return (
    <div data-testid="chart" className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {type === 'line' ? (
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            {yResolved.map((y, i) => (
              <Line
                key={y}
                type="monotone"
                dataKey={y}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : type === 'pie' ? (
          <PieChart>
            <Tooltip />
            <Legend />
            <Pie
              data={data}
              dataKey={yResolved[0]}
              nameKey={xKey}
              cx="50%"
              cy="50%"
              outerRadius={100}
              label
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey={xKey} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend />
            {yResolved.map((y, i) => (
              <Bar key={y} dataKey={y} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
