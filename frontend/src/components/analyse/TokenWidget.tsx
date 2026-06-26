'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, type DailyStats } from '@/lib/api'
import type { LastQueryTokens } from '@/components/analyse/AnalyseTab'

/**
 * Token usage widget (C18) — REAL in Phase 3.
 *
 * The "Last query (In / Out)" row is wired to the most recent answer's token
 * counts (passed down from the Conversation card). The provider/mode line
 * reflects GET /health. The daily totals (model, today In/Out/Queries) and the
 * C29 context-budget bar are now driven by GET /stats/daily — re-fetched on
 * mount and whenever a new answer lands (the `lastTokens` reference changes).
 *
 * The per-query/today COST table is intentionally still a labelled stub: the
 * client-side pricing table is a Phase-4 concern, so cost shows "—" with a clear
 * note rather than a wrong number.
 */
export function TokenWidget({
  provider,
  lastTokens,
}: {
  provider?: string
  lastTokens: LastQueryTokens | null
}) {
  const [stats, setStats] = useState<DailyStats | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    setStatsError(null)
    try {
      setStats(await api.dailyStats())
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'Failed to load usage stats.')
    }
  }, [])

  // Load on mount and refresh whenever a new answer updates lastTokens.
  useEffect(() => {
    void loadStats()
  }, [loadStats, lastTokens])

  const mode =
    provider === 'stub' ? 'Stub (offline)' : provider ? provider : '—'

  const lastQuery = lastTokens ? `${lastTokens.input} / ${lastTokens.output}` : '— / —'

  const today = stats
    ? `${stats.tokens_input} / ${stats.tokens_output} / ${stats.query_count}`
    : '— / — / —'

  const totalToday = stats ? stats.tokens_input + stats.tokens_output : 0
  const budgetPct =
    stats && stats.context_limit > 0
      ? Math.min(100, (totalToday / stats.context_limit) * 100)
      : 0

  return (
    <section
      aria-labelledby="tokens-heading"
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="tokens-heading" className="text-sm font-semibold text-gray-800">
          Token usage
        </h2>
      </div>

      <dl className="space-y-1.5 text-xs">
        <Row label="Provider / mode" value={mode} live />
        <Row label="Model" value={stats?.model ?? '—'} live={!!stats} />
        <Row label="Last query (In / Out)" value={lastQuery} live={!!lastTokens} />
        <Row label="Today (In / Out / Queries)" value={today} live={!!stats} />
      </dl>

      {/* C29 context-budget bar (today's tokens vs the model's context limit). */}
      {stats && stats.context_limit > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex items-center justify-between text-[11px] text-gray-500">
            <span>Today vs context limit</span>
            <span className="tabular-nums">
              {totalToday.toLocaleString()} / {stats.context_limit.toLocaleString()}
            </span>
          </div>
          <div
            role="progressbar"
            aria-label="Token budget used today"
            aria-valuemin={0}
            aria-valuemax={stats.context_limit}
            aria-valuenow={totalToday}
            className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100"
          >
            <div
              className={`h-full transition-all ${
                budgetPct > 90 ? 'bg-red-500' : budgetPct > 70 ? 'bg-amber-500' : 'bg-green-500'
              }`}
              style={{ width: `${budgetPct}%` }}
            />
          </div>
        </div>
      )}

      {statsError && (
        <p role="alert" className="mt-2 text-[11px] text-red-600">
          {statsError}
        </p>
      )}

      {/* Cost table — still a labelled stub (client-side pricing is Phase 4). */}
      <div className="mt-3 border-t border-gray-100 pt-3">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-gray-500">Cost estimate</span>
          <span className="inline-flex items-center gap-1 rounded-full border border-yellow-300 bg-yellow-50 px-2 py-0.5 text-[11px] font-medium text-yellow-800">
            <span aria-hidden="true">●</span> Phase 4 — pricing table
          </span>
        </div>
        <dl className="space-y-1.5 text-xs">
          <Row label="Today cost" value="—" />
        </dl>
        <p className="mt-1 text-xs text-gray-400">
          Per-query and daily cost arrive with the client-side pricing table in a
          later phase.
        </p>
      </div>
    </section>
  )
}

function Row({
  label,
  value,
  live = false,
}: {
  label: string
  value: string
  live?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-gray-500">{label}</dt>
      <dd className={`font-medium tabular-nums ${live ? 'text-gray-800' : 'text-gray-400'}`}>
        {value}
      </dd>
    </div>
  )
}
