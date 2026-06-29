'use client'

import { profileColumnLabel, type ProfileColumn } from '@/lib/api'

const FLAG_LABELS: Record<string, string> = {
  all_null: 'all null',
  'all null': 'all null',
  constant: 'constant',
  high_null: 'high null',
  'high null': 'high null',
}

function flagLabel(flag: string): string {
  return FLAG_LABELS[flag] ?? flag.replace(/_/g, ' ')
}

function formatStat(value: number | string | null): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString()
  return String(value)
}

/**
 * Per-column dataset profile (Phase 2) — rendered from the dataset `profile`
 * computed locally in DuckDB on upload. Tolerant to `column` vs `name` keys.
 */
export function ProfilePanel({ profile }: { profile: ProfileColumn[] | null }) {
  if (!profile || !profile.length) return null

  return (
    <section
      data-testid="profile-panel"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-gray-800">Data profile</h2>
      <p className="mt-1 text-xs text-gray-500">
        Per-column stats computed locally in DuckDB on upload — no raw rows left the machine.
      </p>

      <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Column</th>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Type</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Nulls</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Distinct</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Min</th>
              <th className="px-3 py-2 text-right font-medium text-gray-600">Max</th>
              <th className="px-3 py-2 text-left font-medium text-gray-600">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100" data-testid="profile-rows">
            {profile.map((col, i) => {
              const label = profileColumnLabel(col)
              return (
                <tr key={`${label}-${i}`} data-testid="profile-row">
                  <td className="px-3 py-2 font-medium text-gray-900" data-testid="profile-col-name">
                    {label}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-gray-500">
                      {col.type}
                    </span>
                  </td>
                  <td
                    className="px-3 py-2 text-right font-mono text-gray-800"
                    data-testid="profile-null-count"
                  >
                    {formatStat(col.null_count)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-mono text-gray-800"
                    data-testid="profile-distinct-count"
                  >
                    {formatStat(col.distinct_count)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-700">
                    {formatStat(col.min)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-gray-700">
                    {formatStat(col.max)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {(col.flags ?? []).map(flag => (
                        <span
                          key={flag}
                          data-testid="profile-flag"
                          className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700"
                        >
                          {flagLabel(flag)}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
