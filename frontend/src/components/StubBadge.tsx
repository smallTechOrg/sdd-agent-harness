interface StubBadgeProps {
  label: string
}

export function StubBadge({ label }: StubBadgeProps) {
  return (
    <span className="ml-1 text-xs bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded border border-gray-200">
      {label}
    </span>
  )
}
