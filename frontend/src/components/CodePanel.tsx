'use client'

import { useState } from 'react'
import type { StepEvent } from '../lib/types'

const STEP_LABELS: Record<string, string> = {
  generating_code: 'Generated code',
  running_code: 'Ran code',
  retrying: 'Retried with the error',
  summarising: 'Summarised the result',
}

interface CodePanelProps {
  code: string
  steps: StepEvent[]
}

export function CodePanel({ code, steps }: CodePanelProps) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard unavailable (e.g. insecure context) — no-op.
    }
  }

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white"
      data-testid="code-panel"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        data-testid="code-toggle"
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        <span>Show code &amp; steps</span>
        <svg
          viewBox="0 0 20 20"
          className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div className="border-t border-slate-100 p-4">
          {steps.length > 0 && (
            <ol className="mb-4 list-decimal space-y-1 pl-5 text-sm text-slate-600">
              {steps.map((s, i) => (
                <li key={i}>{STEP_LABELS[s.step] ?? s.step}</li>
              ))}
            </ol>
          )}
          <div className="relative">
            <button
              type="button"
              onClick={copy}
              className="absolute right-2 top-2 rounded-md bg-slate-700 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
            <pre
              data-testid="code-text"
              className="overflow-x-auto rounded-md bg-slate-900 p-4 pr-16 text-sm leading-relaxed text-slate-100"
            >
              <code className="font-mono">{code}</code>
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
