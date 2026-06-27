'use client'

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartSpec } from './types'

const BAR_COLOR = '#2563eb'

// Renders chart_spec from /ask. Phase 1 = bar charts. Defensive about null/empty.
export default function AnswerChart({ spec }: { spec: ChartSpec | null }) {
  if (!spec || !Array.isArray(spec.series) || spec.series.length === 0 || !spec.x) {
    return <p className="text-xs text-gray-400">No chart for this answer.</p>
  }

  // The metric key is the first key in a series row that isn't the x category key.
  const firstRow = spec.series[0]
  const metricKey = Object.keys(firstRow).find(k => k !== spec.x)
  if (!metricKey) {
    return <p className="text-xs text-gray-400">No chart for this answer.</p>
  }

  const unknownType = spec.type && spec.type !== 'bar'

  return (
    <div>
      {unknownType && (
        <p className="mb-2 text-xs text-gray-400">
          Showing as a bar chart (&ldquo;{spec.type}&rdquo; charts arrive in a later phase).
        </p>
      )}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={spec.series} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey={spec.x} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={64} />
            <Tooltip />
            <Bar dataKey={metricKey} fill={BAR_COLOR} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
