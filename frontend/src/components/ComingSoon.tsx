// A clearly-labelled, intentionally-designed stub for a feature that ships in a later phase.
// Greyed/muted so it is never mistaken for a bug.

export function ComingSoonPill({ phase }: { phase?: string }) {
  return (
    <span
      data-testid="coming-soon-pill"
      className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-700"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden />
      Coming soon{phase ? ` · ${phase}` : ''}
    </span>
  )
}

export function ComingSoonCard({
  title,
  description,
  phase,
  icon,
}: {
  title: string
  description: string
  phase?: string
  icon?: string
}) {
  return (
    <div
      data-testid="coming-soon-card"
      aria-disabled
      className="select-none rounded-xl border border-dashed border-gray-300 bg-gray-50/70 p-4 opacity-80"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          {icon && <span className="text-base leading-none" aria-hidden>{icon}</span>}
          <h3 className="text-sm font-semibold text-gray-500">{title}</h3>
        </div>
        <ComingSoonPill phase={phase} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-gray-400">{description}</p>
    </div>
  )
}
