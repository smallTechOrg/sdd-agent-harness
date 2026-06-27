// A muted "Coming soon" pill used to mark intentional, non-functional stubs
// so they are never mistaken for bugs.
export function ComingSoonPill() {
  return (
    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
      Coming soon
    </span>
  )
}
