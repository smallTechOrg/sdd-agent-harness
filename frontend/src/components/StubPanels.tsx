'use client'

// Clearly-labelled, non-functional Phase 2/3 stubs. Each is visibly disabled and
// badged so it reads as "planned", never as a bug.

export function HistoryStub() {
  return (
    <section
      aria-label="Run history (coming soon)"
      className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 opacity-80"
      data-testid="history-stub"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-500">History</h3>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
          Coming in Phase 2
        </span>
      </div>
      <p className="text-sm text-slate-400">
        Your past questions — with their code, result, and cost — will be listed
        here and revisitable.
      </p>
      <ul className="mt-3 space-y-2" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <li
            key={i}
            className="flex items-center gap-3 rounded-md bg-white px-3 py-2"
          >
            <span className="h-2 w-2 rounded-full bg-slate-200" />
            <span className="h-3 flex-1 rounded bg-slate-100" />
          </li>
        ))}
      </ul>
    </section>
  )
}

export function MultiFileStub() {
  return (
    <div data-testid="multifile-stub" className="flex items-center gap-2">
      <button
        type="button"
        disabled
        aria-disabled="true"
        className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-400"
      >
        Add another file / join datasets
      </button>
      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
        Multi-file — Phase 3
      </span>
    </div>
  )
}
