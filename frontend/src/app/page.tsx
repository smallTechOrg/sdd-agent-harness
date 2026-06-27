'use client'

import { useState } from 'react'

import { ResultChart } from './components/ResultChart'
import { ResultTable } from './components/ResultTable'
import { SqlBlock } from './components/SqlBlock'
import { DataSourceBar, SavedDashboards } from './components/StubControls'
import { AnalysisPayload, parseRunEnvelope, RunEnvelope } from './types'

export default function Home() {
  const [question, setQuestion] = useState('')
  const [payload, setPayload] = useState<AnalysisPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    setPayload(null)
    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_text: question }),
      })
      const envelope = (await res.json()) as RunEnvelope
      if (!res.ok) {
        const detail = (envelope as { detail?: { message?: string } }).detail
        setError(
          envelope.data?.error ??
            envelope.error ??
            detail?.message ??
            `Request failed (${res.status})`,
        )
        return
      }
      const parsed = parseRunEnvelope(envelope)
      if (parsed.error) {
        // A graceful agent/SQL failure — show the message, no results.
        setError(parsed.error)
      } else {
        setPayload(parsed)
      }
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-12">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Analysis Console</h1>
        <p className="mt-1 text-sm text-gray-500">
          Ask a question in plain English. Your data stays on this machine —
          only the schema and a few sample rows are sent to the model.
        </p>
      </header>

      <DataSourceBar />

      <form onSubmit={handleSubmit} className="mt-6 space-y-3">
        <textarea
          className="w-full rounded-lg border border-gray-300 p-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          rows={3}
          placeholder="What were total sales by region?"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Analysing…' : 'Ask'}
        </button>
      </form>

      {loading && (
        <div className="mt-6 flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-700">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-300 border-t-blue-600" />
          Analysing…
        </div>
      )}

      {error && !loading && (
        <div
          role="alert"
          className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {payload && !loading && !error && (
        <div className="mt-8 space-y-8">
          <SqlBlock sql={payload.sql} />
          <ResultTable columns={payload.columns} rows={payload.rows} />
          <ResultChart payload={payload} />
        </div>
      )}

      {!payload && !error && !loading && (
        <p className="mt-12 text-center text-sm text-gray-400">
          Ask a question to see the generated SQL, a result table, and a chart.
        </p>
      )}

      <div className="mt-12">
        <SavedDashboards />
      </div>
    </main>
  )
}
