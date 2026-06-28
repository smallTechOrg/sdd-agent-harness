// Shared "coming soon" stub primitives.
// Every deferred feature in spec/ui.md renders through one of these so a stub
// is visibly a labelled, non-interactive preview — never mistaken for a bug.

import type { ReactNode } from 'react'

/** A small grey pill that marks something as a later-phase stub. */
export function ComingSoonBadge({ phase }: { phase?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400" aria-hidden />
      Coming soon{phase ? ` · ${phase}` : ''}
    </span>
  )
}

/**
 * A dashed, greyed-out card wrapping deferred UI. Non-interactive
 * (pointer-events disabled, reduced opacity) with a clear label.
 */
export function StubCard({
  title,
  phase,
  children,
}: {
  title: string
  phase?: string
  children?: ReactNode
}) {
  return (
    <div
      className="select-none rounded-lg border border-dashed border-gray-300 bg-gray-50/60 p-3"
      aria-disabled="true"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-gray-500">{title}</span>
        <ComingSoonBadge phase={phase} />
      </div>
      {children && (
        <div className="pointer-events-none text-xs text-gray-400">{children}</div>
      )}
    </div>
  )
}
