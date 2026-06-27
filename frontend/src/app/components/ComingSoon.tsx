/**
 * A small, visibly-disabled "Coming soon" badge used to label non-functional
 * Phase 1 stubs (Excel upload, Visualize, History) so a user never mistakes a
 * deliberate placeholder for a bug.
 */
export function ComingSoon({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200 ${className}`}
    >
      Coming soon
    </span>
  )
}
