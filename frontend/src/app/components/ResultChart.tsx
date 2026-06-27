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
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'

import {
  AnalysisPayload,
  ChartSpec,
  coerceNumber,
  rowsToObjects,
} from '../types'

const COLORS = ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2']

// Renders a chart from chart_spec. Guards against missing/invalid specs by
// falling back to a quiet "table-only" note (never crashes).
export function ResultChart({ payload }: { payload: AnalysisPayload }) {
  const { chart_spec, columns, rows } = payload

  if (!chart_spec || chart_spec.chart_type === 'table') {
    return (
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-700">Chart</h2>
        <p className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
          This result is best shown as a table — no chart for this question.
        </p>
      </section>
    )
  }

  // A chart needs at least the axis field plus one series and some rows.
  const validSeries = chart_spec.y.filter(s => columns.includes(s))
  const hasAxis = columns.includes(chart_spec.x)
  if (rows.length === 0 || !hasAxis || validSeries.length === 0) {
    return (
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-700">Chart</h2>
        <p className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
          Not enough data to chart this result.
        </p>
      </section>
    )
  }

  const data = rowsToObjects(columns, rows)

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-gray-700">Chart</h2>
      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <ResponsiveContainer width="100%" height={320}>
          {renderChart(chart_spec, validSeries, data)}
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function renderChart(
  spec: ChartSpec,
  series: string[],
  data: Record<string, unknown>[],
) {
  switch (spec.chart_type) {
    case 'line':
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={spec.x} fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Legend />
          {series.map((s, i) => (
            <Line
              key={s}
              type="monotone"
              dataKey={s}
              stroke={COLORS[i % COLORS.length]}
              dot={false}
            />
          ))}
        </LineChart>
      )

    case 'pie': {
      const valueKey = series[0]
      const pieData = data.map(d => ({
        name: String(d[spec.x] ?? ''),
        value: coerceNumber(d[valueKey]),
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
            outerRadius={110}
            label
          >
            {pieData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      )
    }

    case 'scatter': {
      const yKey = series[0]
      const scatterData = data.map(d => ({
        x: coerceNumber(d[spec.x]),
        y: coerceNumber(d[yKey]),
      }))
      return (
        <ScatterChart>
          <CartesianGrid stroke="#e5e7eb" />
          <XAxis type="number" dataKey="x" name={spec.x} fontSize={12} />
          <YAxis type="number" dataKey="y" name={yKey} fontSize={12} />
          <ZAxis range={[60, 60]} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={scatterData} fill={COLORS[0]} />
        </ScatterChart>
      )
    }

    case 'bar':
    default:
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={spec.x} fontSize={12} />
          <YAxis fontSize={12} />
          <Tooltip />
          <Legend />
          {series.map((s, i) => (
            <Bar key={s} dataKey={s} fill={COLORS[i % COLORS.length]} />
          ))}
        </BarChart>
      )
  }
}
