interface StubCardProps {
  title: string
  description: string
}

/**
 * A clearly-labelled, non-functional placeholder for a feature that ships in a
 * later phase. Dimmed with a "Coming soon" badge and inert controls so it reads
 * as an intentional placeholder, never a bug.
 */
export default function StubCard({ title, description }: StubCardProps) {
  return (
    <div
      aria-disabled="true"
      className="select-none rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 opacity-60"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-gray-500">
          Coming soon
        </span>
      </div>
      <p className="mb-3 text-xs text-gray-500">{description}</p>
      <button
        type="button"
        disabled
        tabIndex={-1}
        aria-hidden="true"
        className="cursor-not-allowed rounded border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-400"
      >
        Not available yet
      </button>
    </div>
  )
}
