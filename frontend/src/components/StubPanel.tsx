interface Props { label: string; sublabel?: string }

export default function StubPanel({ label, sublabel }: Props) {
  return (
    <div className="bg-gray-50 border border-dashed border-gray-300 rounded-lg p-4 text-center select-none" aria-label={`${label} — stub`}>
      <p className="text-sm text-gray-400 font-medium">{label}</p>
      {sublabel && <p className="text-xs text-gray-300 mt-1">{sublabel}</p>}
    </div>
  )
}
