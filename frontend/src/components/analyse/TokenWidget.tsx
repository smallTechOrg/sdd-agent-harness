'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, type DailyStats } from '@/lib/api'
import type { LastQueryTokens } from '@/components/analyse/AnalyseTab'

/**
 * Token usage widget (C18) — REAL.
 *
 * The "Last query (In / Out)" row is wired to the most recent answer's token
 * counts (passed down from the Conversation card). The provider/mode line
 * reflects GET /health. The daily totals (model, today In/Out/Queries) and the
 * C29 context-budget bar are driven by GET /stats/daily — re-fetched on mount
 * and whenever a new answer lands (the `lastTokens` reference changes).
 *
 * Cost (C18): a client-side pricing table (below) turns token counts into a
 * currency estimate for the last query and for today. When the active model is
 * not in the table — or its price is deliberately left `null` because we are not
 * confident of the real rate — the cost shows "N/A" rather than a wrong number.
 */

/**
 * Client-side pricing table — USD price PER 1,000,000 TOKENS, split by input
 * (prompt) and output (completion). Keyed by the model id reported in
 * GET /stats/daily (`stats.model`).
 *
 * IMPORTANT: only add a price you are confident is correct. If the real rate is
 * unknown, map the model to `null` so the UI shows "N/A" — never fabricate a
 * number. `gemini-3.1-flash-lite` is intentionally `null`: we do not have a
 * verified published per-token rate for it, so its cost is reported as "N/A".
 */
interface ModelPrice {
  /** USD per 1,000,000 input (prompt) tokens. */
  inputPerMillion: number
  /** USD per 1,000,000 output (completion) tokens. */
  outputPerMillion: number
}

const PRICING_USD_PER_MILLION_TOKENS: Record<string, ModelPrice | null> = {
  // Price unknown / unverified → render "N/A" rather than guess.
  'gemini-3.1-flash-lite': null,
}

/** Resolve a model's price; `undefined` (not in table) and `null` both → no price. */
function priceFor(model: string | undefined): ModelPrice | null {
  if (!model) return null
  return PRICING_USD_PER_MILLION_TOKENS[model] ?? null
}

/** Compute a USD cost from token counts, or null when the model has no price. */
function costUsd(
  price: ModelPrice | null,
  inputTokens: number,
  outputTokens: number,
): number | null {
  if (!price) return null
  return (
    (inputTokens * price.inputPerMillion) / 1_000_000 +
    (outputTokens * price.outputPerMillion) / 1_000_000
  )
}

/** Format a USD cost; "N/A" when the price is unknown. */
function formatCost(value: number | null): string {
  if (value === null) return 'N/A'
  // Show enough precision for tiny per-query costs without trailing noise.
  return `$${value.toFixed(value < 0.01 ? 5 : 4)}`
}
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

  // Cost (C18) via the client-side pricing table. "N/A" when the active model
  // has no known price.
  const price = priceFor(stats?.model)
  const lastQueryCost = lastTokens
    ? formatCost(costUsd(price, lastTokens.input, lastTokens.output))
    : '—'
  const todayCost = stats
    ? formatCost(costUsd(price, stats.tokens_input, stats.tokens_output))
    : '—'

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

      {/* Cost (C18) — client-side pricing table; "N/A" when price is unknown. */}
      <div className="mt-3 border-t border-gray-100 pt-3">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-gray-500">Cost estimate</span>
        </div>
        <dl className="space-y-1.5 text-xs">
          <Row label="Last query cost" value={lastQueryCost} live={!!lastTokens} />
          <Row label="Today cost" value={todayCost} live={!!stats} />
        </dl>
        {price === null && stats && (
          <p className="mt-1 text-[11px] text-gray-400">
            No published price for this model — cost shown as N/A.
          </p>
        )}
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
