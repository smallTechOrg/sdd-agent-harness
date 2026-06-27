'use client'

import ChartPanel, { type ChartSpec } from './ChartPanel'

export interface AgentMessageProps {
  runId?: string
  sqlQuery?: string
  outputText?: string
  insightJson?: Record<string, unknown>
  chartSpecs?: ChartSpec[]
  error?: string
  isLoading?: boolean
}

export default function AgentMessage({
  sqlQuery,
  outputText,
  chartSpecs,
  error,
  isLoading,
}: AgentMessageProps) {
  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2 py-1" aria-label="Loading agent response">
        <div className="h-3 w-3/4 rounded bg-gray-200" />
        <div className="h-3 w-1/2 rounded bg-gray-200" />
        <div className="h-3 w-5/6 rounded bg-gray-200" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-3">
        <p className="text-sm font-medium text-red-700">Error</p>
        <p className="mt-1 text-sm text-red-600">{error}</p>
        <p className="mt-2 text-xs text-red-400 italic">Try rephrasing your question and submitting again.</p>
      </div>
    )
  }

  return (
    <div>
      {sqlQuery && (
        <details className="mb-3">
          <summary className="cursor-pointer select-none text-xs font-medium text-gray-500 hover:text-gray-700">
            SQL used ▸
          </summary>
          <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs text-gray-700 leading-relaxed">
            <code>{sqlQuery}</code>
          </pre>
        </details>
      )}

      {outputText && (
        <p className="mt-1 text-sm text-gray-800 leading-relaxed">{outputText}</p>
      )}

      {chartSpecs && chartSpecs.length > 0 && (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {chartSpecs.map((spec, i) => (
            <ChartPanel key={i} spec={spec} />
          ))}
        </div>
      )}
    </div>
  )
}
