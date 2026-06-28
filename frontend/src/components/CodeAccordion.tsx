'use client'
import { useState } from 'react'
import { ExecutionStep } from '@/types'

interface Props { steps: ExecutionStep[] }

export default function CodeAccordion({ steps }: Props) {
  const [open, setOpen] = useState(false)
  if (steps.length === 0) return null

  return (
    <div className="mt-3 border border-gray-200 rounded-md overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 text-xs font-medium text-gray-600 transition-colors"
        data-testid="code-accordion-toggle"
      >
        <span>Code ({steps.length} step{steps.length > 1 ? 's' : ''})</span>
        <span>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="divide-y divide-gray-100">
          {steps.map((step) => (
            <div key={step.iteration} className="p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${step.success ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  Step {step.iteration + 1} {step.success ? '✓' : '✗'}
                </span>
              </div>
              <pre className="bg-gray-900 text-green-400 text-xs p-3 rounded overflow-x-auto max-h-48">{step.code}</pre>
              {step.stdout && (
                <pre className="mt-2 bg-gray-50 text-gray-700 text-xs p-2 rounded overflow-x-auto max-h-32">stdout: {step.stdout}</pre>
              )}
              {step.stderr && (
                <pre className="mt-2 bg-red-50 text-red-700 text-xs p-2 rounded overflow-x-auto max-h-32">stderr: {step.stderr}</pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
