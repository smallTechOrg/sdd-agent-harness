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

import type { ChartSpec } from '@/lib/types'

// A small, accessible palette reused across series / pie slices.
const PALETTE = [
  '#2563eb', // blue-600
  '#16a34a', // green-600
  '#d97706', // amber-600
  '#dc2626', // red-600
  '#7c3aed', // violet-600
  '#0891b2', // cyan-600
  '#db2777', // pink-600
  '#65a30d', // lime-600
]

// Maps ChartSpec { labels, series:[{name, values}] } into the row-per-label
// shape Recharts expects: [{ label, <seriesName>: value, ... }, ...].
function toRows(spec: ChartSpec): Array<Record<string, string | number>> {
  return spec.labels.map((label, i) => {
    const row: Record<string, string | number> = { label }
    for (const s of spec.series) {
      row[s.name] = s.values[i] ?? 0
    }
    return row
  })
}

export default function ChartRenderer({ spec }: { spec: ChartSpec }) {
  const rows = toRows(spec)

  return (
    <figure className="mt-3 rounded-lg border border-gray-200 bg-white p-3">
      <figcaption className="mb-2 text-xs font-medium text-gray-600">
        {spec.title}
      </figcaption>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(spec, rows)}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

function renderChart(
  spec: ChartSpec,
  rows: Array<Record<string, string | number>>,
) {
  if (spec.type === 'line') {
    return (
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="label" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} width={48} />
        <Tooltip />
        <Legend />
        {spec.series.map((s, i) => (
          <Line
            key={s.name}
            type="monotone"
            dataKey={s.name}
            stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    )
  }

  if (spec.type === 'pie') {
    // Pie uses exactly one series (per the contract); slices come from labels.
    const series = spec.series[0]
    const pieData = spec.labels.map((label, i) => ({
      name: label,
      value: series ? (series.values[i] ?? 0) : 0,
    }))
    return (
      <PieChart>
        <Tooltip />
        <Legend />
        <Pie
          data={pieData}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={90}
          label={{ fontSize: 12 }}
        >
          {pieData.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Pie>
      </PieChart>
    )
  }

  // default: bar
  return (
    <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
      <XAxis dataKey="label" tick={{ fontSize: 12 }} />
      <YAxis tick={{ fontSize: 12 }} width={48} />
      <Tooltip />
      <Legend />
      {spec.series.map((s, i) => (
        <Bar key={s.name} dataKey={s.name} fill={PALETTE[i % PALETTE.length]} radius={[4, 4, 0, 0]} />
      ))}
    </BarChart>
  )
}
