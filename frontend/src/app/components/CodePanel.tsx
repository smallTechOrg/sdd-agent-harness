'use client'

import { useState } from 'react'

interface CodePanelProps {
  code: string
  /** Render expanded by default (used in history detail). */
  defaultOpen?: boolean
}

/**
 * Collapsible "Show code" panel revealing the executed pandas.
 * Collapsed by default per spec/ui.md.
 */
export default function CodePanel({ code, defaultOpen = false }: CodePanelProps) {
  const [open, setOpen] = useState(defaultOpen)
  if (!code) return null
  return (
    <div className="rounded-md border border-gray-200">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
        aria-expanded={open}
      >
        <span>{open ? 'Hide code' : 'Show code'}</span>
        <svg
          className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
        </svg>
      </button>
      {open && (
        <pre className="overflow-x-auto border-t border-gray-200 bg-gray-900 px-3 py-2.5 text-xs leading-relaxed text-gray-100">
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}
