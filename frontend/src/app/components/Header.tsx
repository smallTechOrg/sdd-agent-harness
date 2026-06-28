'use client'

import { ComingSoonBadge } from './Stub'

interface HeaderProps {
  datasetName?: string | null
}

/**
 * App header. Shows the product name, the active dataset (when loaded), and a
 * greyed "daily total" indicator that is a labelled Phase 5 stub (never a real
 * number).
 */
export default function Header({ datasetName }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-gray-200 bg-white px-5 py-3">
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-semibold tracking-tight text-gray-900">DataChat</span>
        <span className="hidden text-xs text-gray-400 sm:inline">
          Local CSV analysis — your data stays on this machine
        </span>
      </div>

      <div className="flex items-center gap-4">
        {datasetName && (
          <span className="hidden max-w-[16rem] truncate rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-700 md:inline">
            {datasetName}
          </span>
        )}
        {/* STUB — daily cost total (Phase 5). Greyed, non-interactive, no real number. */}
        <div
          className="flex items-center gap-2 rounded-md border border-dashed border-gray-300 bg-gray-50 px-2.5 py-1"
          aria-disabled="true"
          title="Running daily cost total — coming in a later phase"
        >
          <span className="text-xs text-gray-400">Daily total —</span>
          <ComingSoonBadge phase="P5" />
        </div>
      </div>
    </header>
  )
}
