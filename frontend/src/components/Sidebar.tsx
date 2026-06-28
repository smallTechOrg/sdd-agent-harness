'use client'

import type { DatasetSummary } from '../lib/api'
import { DatasetList } from './DatasetList'
import { StubBadge } from './StubPanel'

interface SidebarProps {
  datasets: DatasetSummary[]
  activeId: string | null
  listLoading: boolean
  listError: string | null
  onSelect: (id: string) => void
}

export function Sidebar({ datasets, activeId, listLoading, listError, onSelect }: SidebarProps) {
  return (
    <aside data-testid="sidebar" className="w-full shrink-0 lg:w-64">
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-900">Datasets</h2>

        {/* REAL in Phase 2: switchable list from GET /datasets, newest first. */}
        <div className="mt-3">
          <DatasetList
            datasets={datasets}
            activeId={activeId}
            loading={listLoading}
            error={listError}
            onSelect={onSelect}
          />
        </div>
      </div>

      {/* STUB: compare another file (Phase 4) */}
      <div data-stub="true" aria-disabled="true" className="pointer-events-none mt-4 select-none">
        <button
          disabled
          className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-2.5 text-sm font-medium text-gray-400"
        >
          Compare another file
          <StubBadge phase="Phase 4" />
        </button>
      </div>

      {/* STUB: column notes (Phase 5) */}
      <div
        data-stub="true"
        aria-disabled="true"
        className="pointer-events-none mt-4 select-none rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-gray-400">Column notes</span>
          <StubBadge phase="Phase 5" />
        </div>
        <p className="mt-2 text-xs text-gray-400">
          Attach business rules (e.g. “revenue is in thousands”) for the agent to use.
        </p>
      </div>

      {/* STUB: daily cost (Phase 6) — per-question cost is real, shown in show-its-work */}
      <div
        data-stub="true"
        aria-disabled="true"
        title="Daily cost roll-up — coming soon"
        className="pointer-events-none mt-4 select-none rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-gray-400">Today’s spend</span>
          <StubBadge phase="Phase 6" />
        </div>
        <div className="mt-1 text-2xl font-bold text-gray-300" data-testid="daily-cost">
          —
        </div>
      </div>
    </aside>
  )
}
