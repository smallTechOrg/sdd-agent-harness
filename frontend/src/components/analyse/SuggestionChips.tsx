'use client'

/**
 * Follow-up suggestion chips (Phase 3 — C22).
 *
 * Renders the latest answer's `suggested_questions` as clickable chips. Clicking
 * a chip submits it as the next question in the SAME session (the parent owns
 * that submission). Renders nothing when there are no suggestions, so an empty
 * list never leaves a dangling label.
 */
export function SuggestionChips({
  suggestions,
  onPick,
  disabled = false,
}: {
  suggestions: string[]
  onPick: (question: string) => void
  disabled?: boolean
}) {
  const items = (suggestions ?? []).filter(s => s && s.trim().length > 0)
  if (items.length === 0) return null

  return (
    <div className="mt-3">
      <p className="mb-1.5 text-[11px] font-medium text-gray-500">Follow-up suggestions</p>
      <div className="flex flex-wrap gap-2">
        {items.map((s, i) => (
          <button
            key={`${i}-${s}`}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:border-blue-300 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
