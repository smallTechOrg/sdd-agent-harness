'use client'

// Labelled NON-FUNCTIONAL stubs for features shipping in later phases.
// These must always read as "Coming soon" — styled, disabled, badged —
// never as broken or as a bug.

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
      {children}
    </span>
  )
}

// Top-right header button (Phase 4).
export function ConnectDatabaseButton() {
  return (
    <button
      type="button"
      disabled
      title="Connect a live database — coming soon"
      className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-400"
    >
      Connect a live database ▸
      <Badge>Coming soon</Badge>
    </button>
  )
}

// Sidebar group of later-phase features (Phases 2 & 3).
export function ComingSoonPanel() {
  return (
    <div className="space-y-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400">
        Coming soon
      </p>

      {/* Deep memory — Phase 2 */}
      <div className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-500">Deep memory</p>
          <p className="truncate text-xs text-gray-400">
            Remembers across the whole chat
          </p>
        </div>
        <Badge>Coming soon</Badge>
      </div>

      {/* Auto-insights — Phase 3 */}
      <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3 opacity-80">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-gray-500">Auto-insights</p>
          <Badge>Coming soon</Badge>
        </div>
        <p className="mt-1 text-xs text-gray-400">
          Insights it finds on its own — coming soon
        </p>
      </div>
    </div>
  )
}

// Disabled chart-type toggle under the input (manual chart control deferred).
export function ChartTypeToggle() {
  const types: Array<'bar' | 'line' | 'pie'> = ['bar', 'line', 'pie']
  return (
    <div
      className="inline-flex items-center gap-2"
      title="The agent picks the best chart — manual control coming soon"
    >
      <span className="text-xs text-gray-400">Chart type</span>
      <div className="inline-flex overflow-hidden rounded-lg border border-gray-200">
        {types.map((t, i) => (
          <button
            key={t}
            type="button"
            disabled
            aria-disabled="true"
            className={[
              'cursor-not-allowed bg-gray-50 px-2.5 py-1 text-xs capitalize text-gray-400',
              i > 0 ? 'border-l border-gray-200' : '',
            ].join(' ')}
          >
            {t}
          </button>
        ))}
      </div>
      <Badge>Coming soon</Badge>
    </div>
  )
}
