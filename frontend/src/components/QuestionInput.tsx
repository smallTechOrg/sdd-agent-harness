'use client'

import { useState } from 'react'

import { ChartTypeToggle } from './ComingSoon'

interface Props {
  disabled: boolean
  pending: boolean
  onAsk: (question: string) => void
}

export default function QuestionInput({ disabled, pending, onAsk }: Props) {
  const [value, setValue] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const q = value.trim()
    if (!q || disabled || pending) return
    onAsk(q)
    setValue('')
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
      <form onSubmit={submit} className="mx-auto flex max-w-3xl items-center gap-2">
        <label htmlFor="question" className="sr-only">
          Ask a question about your data
        </label>
        <input
          id="question"
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          disabled={disabled}
          placeholder={
            disabled
              ? 'Upload a file to start asking questions…'
              : 'Ask a question about your data…'
          }
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400"
        />
        <button
          type="submit"
          disabled={disabled || pending || !value.trim()}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? 'Asking…' : 'Ask'}
        </button>
      </form>
      <div className="mx-auto mt-2 flex max-w-3xl justify-start">
        <ChartTypeToggle />
      </div>
    </div>
  )
}
