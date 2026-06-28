'use client'

import { useState } from 'react'
import { type DatasetProfile, type HistoryItem } from '@/lib/api'
import HistoryBrowser from './HistoryBrowser'

interface ProfilePanelProps {
  profile: DatasetProfile
  history: HistoryItem[]
  sampleRowCount: number
}

type Tab = 'profile' | 'history'

function fmtNum(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number.isInteger(v)
    ? v.toLocaleString()
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/**
 * Right observability panel: dataset profile (rows + per-column stats + sample
 * rows), run-history browser, and the "what was sent to the model" reassurance
 * line reinforcing the privacy promise.
 */
export default function ProfilePanel({ profile, history, sampleRowCount }: ProfilePanelProps) {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-gray-200 bg-white">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 text-xs font-medium">
        <button
          type="button"
          onClick={() => setTab('profile')}
          className={`flex-1 px-3 py-2.5 ${
            tab === 'profile'
              ? 'border-b-2 border-blue-600 text-blue-700'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Profile
        </button>
        <button
          type="button"
          onClick={() => setTab('history')}
          className={`flex-1 px-3 py-2.5 ${
            tab === 'history'
              ? 'border-b-2 border-blue-600 text-blue-700'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          History {history.length > 0 && <span className="text-gray-400">({history.length})</span>}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'profile' ? (
          <ProfileContent profile={profile} sampleRowCount={sampleRowCount} />
        ) : (
          <HistoryBrowser history={history} />
        )}
      </div>
    </aside>
  )
}

function ProfileContent({
  profile,
  sampleRowCount,
}: {
  profile: DatasetProfile
  sampleRowCount: number
}) {
  return (
    <div className="space-y-4">
      {/* Row count */}
      <div className="rounded-md bg-gray-50 px-3 py-2">
        <div className="text-[10px] font-medium uppercase tracking-wide text-gray-400">Rows</div>
        <div className="text-lg font-semibold tabular-nums text-gray-900">
          {profile.row_count.toLocaleString()}
        </div>
      </div>

      {/* Columns */}
      <div>
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
          Columns ({profile.columns.length})
        </h3>
        <div className="space-y-1.5">
          {profile.columns.map((col) => (
            <div key={col.name} className="rounded-md border border-gray-200 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium text-gray-800" title={col.name}>
                  {col.name}
                </span>
                <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500">
                  {col.dtype}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-400">
                <span>missing: {col.missing.toLocaleString()}</span>
                {col.distinct != null && <span>distinct: {col.distinct.toLocaleString()}</span>}
                {col.min != null && <span>min: {fmtNum(col.min)}</span>}
                {col.max != null && <span>max: {fmtNum(col.max)}</span>}
                {col.mean != null && <span>mean: {fmtNum(col.mean)}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sample rows */}
      {profile.sample_rows.length > 0 && (
        <div>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-400">
            Sample rows
          </h3>
          <div className="overflow-x-auto rounded-md border border-gray-200">
            <table className="min-w-full text-[10px]">
              <thead>
                <tr className="bg-gray-50 text-left text-gray-500">
                  {profile.columns.map((c) => (
                    <th key={c.name} className="whitespace-nowrap px-2 py-1 font-medium">
                      {c.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {profile.sample_rows.slice(0, 5).map((row, ri) => (
                  <tr key={ri} className="even:bg-gray-50/50">
                    {profile.columns.map((c) => (
                      <td key={c.name} className="whitespace-nowrap px-2 py-1 text-gray-700">
                        {row[c.name] == null ? '—' : String(row[c.name])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Privacy reassurance — "what was sent to the model" */}
      <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-green-800">
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
            />
          </svg>
          What was sent to the model
        </div>
        <p className="mt-1 text-[11px] leading-snug text-green-700">
          Only the {profile.columns.length} column names + types and {sampleRowCount} sample{' '}
          {sampleRowCount === 1 ? 'row' : 'rows'} left this machine. All{' '}
          {profile.row_count.toLocaleString()} rows stay local and are processed by pandas here.
        </p>
      </div>
    </div>
  )
}
