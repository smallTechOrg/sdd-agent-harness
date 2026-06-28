'use client'

import type { ErrorEvent } from '../lib/types'

interface StuckPanelProps {
  error: ErrorEvent
}

// The agent's "here's what I tried" message + the attempted code — never a raw crash.
export function StuckPanel({ error }: StuckPanelProps) {
  return (
    <section
      aria-label="Couldn't answer"
      role="alert"
      className="space-y-4 rounded-xl border border-amber-200 bg-amber-50 p-6 shadow-sm"
      data-testid="stuck-panel"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-200 text-amber-800"
          aria-hidden="true"
        >
          !
        </span>
        <div>
          <h3 className="text-base font-semibold text-amber-900">
            I couldn&apos;t finish this one
          </h3>
          <p className="mt-1 text-sm text-amber-800">{error.message}</p>
        </div>
      </div>

      {error.code_attempted && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-amber-700">
            What I tried
          </p>
          <pre className="overflow-x-auto rounded-md bg-slate-900 p-4 text-sm leading-relaxed text-slate-100">
            <code className="font-mono">{error.code_attempted}</code>
          </pre>
        </div>
      )}

      <p className="text-sm text-amber-800">
        Try rephrasing the question, or ask something more specific about a
        column you can see in the profile above.
      </p>
    </section>
  )
}
