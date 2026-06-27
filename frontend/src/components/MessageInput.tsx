'use client'

import { useState, useRef, type KeyboardEvent } from 'react'

interface MessageInputProps {
  onSubmit: (question: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function MessageInput({
  onSubmit,
  disabled = false,
  placeholder = 'Ask a question about your data…',
}: MessageInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = () => {
    const q = value.trim()
    if (!q || disabled) return
    onSubmit(q)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const maxRows = 3 * 24 // ~3 lines at 24px line-height
    el.style.height = Math.min(el.scrollHeight, maxRows) + 'px'
  }

  return (
    <div className="flex items-end gap-2 border-t border-gray-200 bg-white px-4 py-3">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 resize-none overflow-hidden rounded-xl border border-gray-300 px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        style={{ minHeight: '2.5rem' }}
      />
      <button
        type="button"
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        className="shrink-0 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Analyze
      </button>
    </div>
  )
}
