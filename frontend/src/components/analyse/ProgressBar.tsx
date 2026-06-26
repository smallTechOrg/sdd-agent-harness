'use client'

/**
 * Live agent-progress bar (Phase 3).
 *
 * Driven by GET /runs/current polled ~1/s while an ask is in flight: shows the
 * current run status and an `iteration_count / max_iterations` bar. When the
 * iteration count is not yet known (or max is 0) it shows an indeterminate
 * sliver rather than a misleading 0%.
 *
 * `role="progressbar"` + `aria-valuenow/min/max` keep it accessible; the label
 * reads "Checking…" during the C26 pre-flight and "Thinking…" once running.
 */
export function ProgressBar({
  label,
  iteration,
  max,
}: {
  label: string
  iteration: number | null
  max: number | null
}) {
  const known = iteration != null && max != null && max > 0
  const pct = known ? Math.min(100, (iteration / max) * 100) : null

  return (
    <div className="mt-2" aria-live="polite">
      <div className="mb-1 flex items-center justify-between text-[11px] text-gray-500">
        <span className="inline-flex items-center gap-1.5">
          <Spinner /> {label}
        </span>
        {known && (
          <span className="tabular-nums">
            Step {iteration} / {max}
          </span>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Agent progress"
        aria-valuemin={0}
        aria-valuemax={max ?? 0}
        aria-valuenow={iteration ?? 0}
        className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100"
      >
        <div
          className="h-full bg-blue-500 transition-all"
          style={{ width: pct != null ? `${pct}%` : '15%' }}
        />
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  )
}
