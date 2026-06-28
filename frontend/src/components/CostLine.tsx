'use client'

import type { Usage } from '../lib/types'

interface CostLineProps {
  usage: Usage
  dailyTotalUsd: number
}

function fmtUsd(n: number, digits = 4): string {
  return `$${n.toFixed(digits)}`
}

export function CostLine({ usage, dailyTotalUsd }: CostLineProps) {
  const totalTokens =
    (usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0)
  return (
    <p
      className="text-sm text-slate-500"
      data-testid="cost-line"
    >
      This question:{' '}
      <span className="font-medium text-slate-700">
        {totalTokens.toLocaleString()} tokens
      </span>{' '}
      · ~{fmtUsd(usage.cost_usd ?? 0)} · Today:{' '}
      <span className="font-medium text-slate-700">
        {fmtUsd(dailyTotalUsd ?? 0, 4)}
      </span>
    </p>
  )
}
