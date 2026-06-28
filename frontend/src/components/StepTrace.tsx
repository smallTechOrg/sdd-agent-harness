'use client'

import { useEffect, useRef, useState } from 'react'
import type { StepEvent } from '../lib/types'

const STEP_LABELS: Record<string, string> = {
  generating_code: 'Generating code',
  running_code: 'Running code',
  retrying: 'Retrying with the error',
  summarising: 'Summarising',
}

interface StepTraceProps {
  steps: StepEvent[]
  // When true the run is active and the elapsed timer ticks.
  active: boolean
}

export function StepTrace({ steps, active }: StepTraceProps) {
  const [elapsedMs, setElapsedMs] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) return
    if (startRef.current === null) startRef.current = Date.now()
    const id = setInterval(() => {
      if (startRef.current !== null) {
        setElapsedMs(Date.now() - startRef.current)
      }
    }, 100)
    return () => clearInterval(id)
  }, [active])

  useEffect(() => {
    if (!active) startRef.current = null
  }, [active])

  return (
    <section
      aria-label="Progress"
      aria-live="polite"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      data-testid="step-trace"
    >
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">
          Step {steps.length}
          {active ? ' — working…' : ' — done'}
        </p>
        <p className="font-mono text-sm text-slate-500" data-testid="elapsed">
          {(elapsedMs / 1000).toFixed(1)}s
        </p>
      </div>
      <ol className="space-y-2">
        {steps.map((s, i) => {
          const isLast = i === steps.length - 1
          const spinning = active && isLast
          return (
            <li key={i} className="flex items-center gap-3 text-sm">
              {spinning ? (
                <span
                  className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
                  aria-hidden="true"
                />
              ) : (
                <span
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600"
                  aria-hidden="true"
                >
                  <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none">
                    <path
                      d="M2.5 6.5 5 9l4.5-5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
              )}
              <span className="text-slate-700">
                {STEP_LABELS[s.step] ?? s.step}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
