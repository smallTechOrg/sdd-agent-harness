'use client'

import { ComingSoonBadge } from './Stub'

interface SidebarProps {
  datasetName?: string | null
  rowCount?: number | null
}

/**
 * Left library sidebar.
 *
 * Phase 1: shows the single active dataset (REAL), plus a clearly-labelled,
 * disabled "Your library — coming soon" section with greyed non-interactive
 * placeholder rows and a disabled "Save cleaned dataset" button (Phase 3).
 * No fake data — placeholder rows are visibly empty/greyed.
 */
export default function Sidebar({ datasetName, rowCount }: SidebarProps) {
  return (
    <aside className="flex w-60 shrink-0 flex-col gap-4 border-r border-gray-200 bg-white p-4">
      {/* Active dataset — REAL */}
      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          Active dataset
        </h2>
        {datasetName ? (
          <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2">
            <div className="truncate text-sm font-medium text-gray-900" title={datasetName}>
              {datasetName}
            </div>
            {rowCount != null && (
              <div className="mt-0.5 text-xs text-gray-500">
                {rowCount.toLocaleString()} rows
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-gray-200 px-3 py-2 text-xs text-gray-400">
            No dataset yet — upload a CSV to begin.
          </div>
        )}
      </div>

      {/* STUB — persistent multi-dataset library (Phase 3) */}
      <div className="select-none" aria-disabled="true">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            Your library
          </h2>
          <ComingSoonBadge phase="P3" />
        </div>
        <div className="pointer-events-none space-y-1.5 opacity-70">
          {['', ''].map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-2 rounded-md border border-dashed border-gray-200 bg-gray-50 px-3 py-2"
            >
              <div className="h-3 w-3 rounded-sm bg-gray-200" />
              <div className="h-2.5 flex-1 rounded bg-gray-200" />
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] leading-snug text-gray-400">
          Switch between saved datasets across days — coming in a later phase.
        </p>
      </div>

      {/* STUB — save derived/cleaned dataset (Phase 3) */}
      <div className="mt-auto">
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="w-full cursor-not-allowed rounded-md border border-dashed border-gray-300 bg-gray-50 px-3 py-2 text-xs font-medium text-gray-400"
          title="Save a cleaned/derived dataset — coming in a later phase"
        >
          Save cleaned dataset
        </button>
        <p className="mt-1 text-center text-[11px] text-gray-400">Coming soon · P3</p>
      </div>
    </aside>
  )
}
