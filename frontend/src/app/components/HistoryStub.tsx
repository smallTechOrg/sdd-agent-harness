import { ComingSoon } from './ComingSoon'

/**
 * Labelled, non-functional placeholder for the deferred query-history feature.
 * Visibly greyed-out and tagged "Coming soon" so it is never mistaken for a bug.
 */
export function HistoryStub() {
  return (
    <section
      aria-label="History (coming soon)"
      className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 p-6"
    >
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-400">History</h2>
        <ComingSoon />
      </div>
      <p className="mt-2 text-sm text-slate-400">Your past questions will appear here — Coming soon.</p>
      <ul className="mt-4 space-y-2" aria-hidden>
        {[0, 1].map((i) => (
          <li key={i} className="h-9 rounded-lg border border-slate-200 bg-white/50" />
        ))}
      </ul>
    </section>
  )
}
