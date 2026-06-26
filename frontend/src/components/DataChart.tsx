'use client'

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
} from 'recharts'

export interface ChartSpec {
  type: 'bar' | 'line' | 'pie' | 'scatter' | 'empty'
  title?: string
  xKey?: string
  yKey?: string
  nameKey?: string
  valueKey?: string
  data: Array<Record<string, unknown>>
  message?: string
}

const COLORS = [
  '#6366f1',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#f97316',
]

interface DataChartProps {
  chartSpec: ChartSpec
}

export function DataChart({ chartSpec }: DataChartProps) {
  if (chartSpec.type === 'empty') {
    return (
      <div className="flex items-center justify-center h-[300px] bg-gray-50 rounded-lg border border-gray-200 text-gray-400 text-sm">
        {chartSpec.message ?? 'No chart data available.'}
      </div>
    )
  }

  if (!chartSpec.data || chartSpec.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] bg-gray-50 rounded-lg border border-gray-200 text-gray-400 text-sm">
        No data to display.
      </div>
    )
  }

  if (chartSpec.type === 'bar') {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartSpec.data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={chartSpec.xKey} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          <Bar dataKey={chartSpec.yKey ?? ''} fill={COLORS[0]} />
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chartSpec.type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartSpec.data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={chartSpec.xKey} tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey={chartSpec.yKey ?? ''}
            stroke={COLORS[0]}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (chartSpec.type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={chartSpec.data}
            dataKey={chartSpec.valueKey ?? ''}
            nameKey={chartSpec.nameKey ?? ''}
            cx="50%"
            cy="50%"
            outerRadius={110}
            label
          >
            {chartSpec.data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  if (chartSpec.type === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={chartSpec.xKey} type="number" name={chartSpec.xKey} tick={{ fontSize: 12 }} />
          <YAxis dataKey={chartSpec.yKey} type="number" name={chartSpec.yKey} tick={{ fontSize: 12 }} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Legend />
          <Scatter data={chartSpec.data} fill={COLORS[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  return (
    <div className="flex items-center justify-center h-[300px] bg-gray-50 rounded-lg border border-gray-200 text-gray-400 text-sm">
      Unknown chart type: {chartSpec.type}
    </div>
  )
}
