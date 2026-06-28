'use client'

import { STEP_ORDER, stepLabel } from '@/lib/sse'

interface StepIndicatorProps {
  /** Current active step id, or null when idle. */
  current: string | null
}

/**
 * Streaming progress: Planning… → Generating code… → Running locally… →
 * Writing answer… Highlights the active step and marks earlier ones done.
 * Never a bare spinner — always shows where we are.
 */
export default function StepIndicator({ current }: StepIndicatorProps) {
  if (!current) return null
  const currentIndex = STEP_ORDER.indexOf(current as (typeof STEP_ORDER)[number])

  return (
    <div className="flex flex-wrap items-center gap-2" role="status" aria-live="polite">
      {STEP_ORDER.map((step, i) => {
        const done = currentIndex > i
        const active = currentIndex === i
        return (
          <div key={step} className="flex items-center gap-2">
            <div
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                active
                  ? 'bg-blue-100 text-blue-700'
                  : done
                    ? 'bg-green-50 text-green-700'
                    : 'bg-gray-100 text-gray-400'
              }`}
            >
              {active ? (
                <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" aria-hidden />
              ) : done ? (
                <span className="text-green-600" aria-hidden>
                  ✓
                </span>
              ) : (
                <span className="h-2 w-2 rounded-full bg-gray-300" aria-hidden />
              )}
              {stepLabel(step)}
            </div>
            {i < STEP_ORDER.length - 1 && (
              <span className="text-gray-300" aria-hidden>
                →
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
