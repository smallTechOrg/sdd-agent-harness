'use client'

interface StubNavLinkProps {
  label: string
  phase: string
  message: string
}

export function StubNavLink({ label, phase, message }: StubNavLinkProps) {
  return (
    <button
      type="button"
      onClick={() => alert(message)}
      className="text-gray-400 cursor-pointer flex items-center gap-1 bg-transparent border-0 p-0"
      title={`Coming in ${phase}`}
    >
      {label}
      <span className="text-xs bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded ml-1">
        [{phase}]
      </span>
    </button>
  )
}
