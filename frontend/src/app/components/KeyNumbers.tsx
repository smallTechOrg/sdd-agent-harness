'use client'

import { type KeyNumbers as KeyNumbersData } from '@/lib/api'

interface KeyNumbersProps {
  numbers: KeyNumbersData
}

function format(v: string | number | boolean | null): string {
  if (v == null) return '—'
  if (typeof v === 'number') {
    return Number.isInteger(v)
      ? v.toLocaleString()
      : v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}

/** Headline aggregates strip from `done.key_numbers`. */
export default function KeyNumbers({ numbers }: KeyNumbersProps) {
  const entries = Object.entries(numbers)
  if (entries.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([label, value]) => (
        <div
          key={label}
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5"
        >
          <div className="text-[10px] font-medium uppercase tracking-wide text-gray-400">
            {label}
          </div>
          <div className="text-sm font-semibold tabular-nums text-gray-900">
            {format(value)}
          </div>
        </div>
      ))}
    </div>
  )
}
