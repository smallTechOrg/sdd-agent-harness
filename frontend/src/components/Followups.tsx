'use client'

/**
 * Follow-up suggestion chips (Phase 2). Clicking a chip submits it as the NEXT
 * question via the same ask handler. Disabled while a request is in flight.
 */
export function Followups({
  followups,
  disabled,
  onPick,
}: {
  followups: string[] | null
  disabled: boolean
  onPick: (question: string) => void
}) {
  const chips = (followups ?? []).filter(q => typeof q === 'string' && q.trim().length > 0)
  if (!chips.length) return null

  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
        Suggested follow-ups
      </div>
      <div className="flex flex-wrap gap-2" data-testid="followup-chips">
        {chips.map((q, i) => (
          <button
            key={`${q}-${i}`}
            type="button"
            data-testid="followup-chip"
            disabled={disabled}
            onClick={() => onPick(q)}
            className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:border-blue-300 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden>💡</span>
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
