interface SpinnerProps {
  label?: string
}

export default function Spinner({ label }: SpinnerProps) {
  return (
    <span className="inline-flex items-center gap-2" role="status" aria-live="polite">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
      />
      {label && <span>{label}</span>}
    </span>
  )
}
