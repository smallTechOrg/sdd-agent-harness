'use client'

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

export interface ChartSpec {
  chart_type: 'line' | 'bar' | 'histogram' | 'scatter'
  title: string
  // Backend returns x_key/y_key (flat); accept both formats
  x_key?: string
  y_key?: string
  x_axis?: { key: string; label?: string }
  y_axes?: Array<{ key: string; label?: string }>
  data: Record<string, unknown>[]
  sampled?: boolean
}

interface ChartPanelProps {
  spec: ChartSpec
}

export default function ChartPanel({ spec }: ChartPanelProps) {
  // Support flat x_key/y_key (backend) and nested x_axis.key/y_axes[0].key
  const xKey = spec.x_key ?? spec.x_axis?.key ?? 'x'
  const yKey = spec.y_key ?? spec.y_axes?.[0]?.key ?? 'y'
  const PRIMARY = '#6366f1'

  const renderChart = () => {
    switch (spec.chart_type) {
      case 'line':
        return (
          <LineChart data={spec.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="monotone" dataKey={yKey} stroke={PRIMARY} dot={false} strokeWidth={2} />
          </LineChart>
        )
      case 'bar':
      case 'histogram':
        return (
          <BarChart data={spec.data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={yKey} fill={PRIMARY} radius={[3, 3, 0, 0]} />
          </BarChart>
        )
      case 'scatter':
        return (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey={xKey} name={xKey} tick={{ fontSize: 11 }} />
            <YAxis dataKey={yKey} name={yKey} tick={{ fontSize: 11 }} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={spec.data} fill={PRIMARY} />
          </ScatterChart>
        )
      default:
        return null
    }
  }

  return (
    <div className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm">
      <p className="mb-2 text-sm font-medium text-gray-700">{spec.title}</p>
      {spec.sampled && (
        <p className="mb-1 text-xs italic text-gray-400">(sampled to 500 points)</p>
      )}
      <div className="w-full h-64">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart() ?? <div />}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
