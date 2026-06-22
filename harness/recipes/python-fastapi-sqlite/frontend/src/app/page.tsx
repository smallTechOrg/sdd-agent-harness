'use client'

import { useState } from 'react'

export default function Home() {
  const [inputText, setInputText] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!inputText.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_text: inputText }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail?.message ?? `Request failed (${res.status})`)
      } else {
        setResult(data.data.output_text)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>Text Transform</h1>
      <form onSubmit={handleSubmit}>
        <textarea
          value={inputText}
          onChange={e => setInputText(e.target.value)}
          placeholder="Enter text to transform…"
          disabled={loading}
        />
        <br />
        <button type="submit" disabled={loading || !inputText.trim()}>
          {loading ? 'Transforming…' : 'Transform'}
        </button>
      </form>

      {error && <div className="error">⚠ {error}</div>}
      {result && <div className="result">{result}</div>}

      <div className="stub-notice">
        🚧 <strong>Coming in Phase 2:</strong> <a href="/app/history/">Run History</a> — view past transforms once the history endpoint is wired up.
      </div>
    </main>
  )
}
