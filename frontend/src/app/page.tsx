'use client'

import { useState } from 'react'

type ResultTable = {
  columns: string[]
  rows: unknown[][]
}

type RunData = {
  run_id: string
  status: string
  answer: string | null
  explanation: string | null
  generated_code: string | null
  result_table: ResultTable | null
  truncated: boolean
  error: string | null
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default function Home() {
  const [csvText, setCsvText] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')

  const [result, setResult] = useState<RunData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const canRun = !!csvText && question.trim().length > 0 && !loading

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    setFileError(null)
    setCsvText(null)
    setFileName(null)
    if (!file) return

    const isCsv =
      file.type === 'text/csv' ||
      file.type === 'application/vnd.ms-excel' ||
      file.name.toLowerCase().endsWith('.csv')
    if (!isCsv) {
      setFileError('Please choose a .csv file.')
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      setCsvText(typeof reader.result === 'string' ? reader.result : '')
      setFileName(file.name)
    }
    reader.onerror = () => {
      setFileError('Could not read that file. Please try again.')
    }
    reader.readAsText(file)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!csvText || !question.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text: csvText, question: question.trim() }),
      })
      const body = await res.json()
      if (!res.ok) {
        setError(body.detail?.message ?? `Request failed (${res.status})`)
        return
      }
      const data: RunData | undefined = body.data
      if (!data) {
        setError('The server returned an unexpected response.')
        return
      }
      setResult(data)
      if (data.status === 'failed' || data.error) {
        setError(data.error ?? 'The analysis failed. Please try a different question.')
      }
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setLoading(false)
    }
  }

  const showAnswer = result && result.status !== 'failed' && !result.error
  const hasRun = result !== null || error !== null

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      {/* Title + intro */}
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">Local Data Analyst</h1>
        <p className="mt-2 text-sm text-gray-600">
          Your data stays on this machine — only the column schema and a small sample are sent to
          the model.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* CSV upload */}
        <div className="space-y-2">
          <label htmlFor="csv-file" className="block text-sm font-medium text-gray-800">
            1. Upload a CSV
          </label>
          <input
            id="csv-file"
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            disabled={loading}
            className="block w-full text-sm text-gray-700 file:mr-4 file:rounded-lg file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100 disabled:opacity-50"
          />
          {fileName && (
            <p className="text-xs text-green-700">
              <span className="font-medium">{fileName}</span> — loaded
            </p>
          )}
          {fileError && (
            <p className="text-xs text-red-600" role="alert">
              {fileError}
            </p>
          )}
        </div>

        {/* Question input */}
        <div className="space-y-2">
          <label htmlFor="question" className="block text-sm font-medium text-gray-800">
            2. Ask a question
          </label>
          <textarea
            id="question"
            className="w-full rounded-lg border border-gray-300 p-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:opacity-60"
            rows={3}
            placeholder="e.g. What were total sales by region, highest first?"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            disabled={loading}
          />
        </div>

        {/* Run button */}
        <button
          type="submit"
          disabled={!canRun}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
              aria-hidden="true"
            />
          )}
          {loading ? 'Analyzing…' : 'Run analysis'}
        </button>
      </form>

      {/* Empty state */}
      {!hasRun && !loading && (
        <p className="mt-10 rounded-lg border border-dashed border-gray-300 bg-white px-4 py-8 text-center text-sm text-gray-400">
          Upload a CSV and ask a question to get started.
        </p>
      )}

      {/* Error card (handled failure / network / HTTP) */}
      {error && (
        <div
          className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium">Something went wrong</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {/* Answer card (REAL) */}
      {showAnswer && (
        <section className="mt-8 space-y-6">
          <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Answer</h2>
            <p className="mt-2 whitespace-pre-wrap text-lg font-semibold text-gray-900">
              {result.answer}
            </p>
            {result.explanation && (
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
                {result.explanation}
              </p>
            )}
          </div>

          {/* "Show its work" panel (REAL) — always visible alongside answer */}
          <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
              Show its work
            </h2>

            {result.generated_code && (
              <div className="mt-3">
                <p className="mb-1 text-xs font-medium text-gray-600">Generated pandas code</p>
                <pre className="overflow-x-auto rounded-md bg-gray-900 p-4 text-xs leading-relaxed text-gray-100">
                  <code>{result.generated_code}</code>
                </pre>
              </div>
            )}

            {result.result_table && result.result_table.columns.length > 0 && (
              <div className="mt-4">
                <p className="mb-1 text-xs font-medium text-gray-600">Result</p>
                <div className="overflow-x-auto rounded-md border border-gray-200">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        {result.result_table.columns.map((col, i) => (
                          <th
                            key={i}
                            className="px-3 py-2 text-left font-semibold text-gray-700"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {result.result_table.rows.map((row, ri) => (
                        <tr key={ri} className="even:bg-gray-50/50">
                          {row.map((cell, ci) => (
                            <td key={ci} className="px-3 py-2 text-gray-800">
                              {formatCell(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {result.truncated && (
                  <p className="mt-2 text-xs text-gray-500">
                    (showing first {result.result_table.rows.length} rows)
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Generated code on a handled failure (still show the attempt) */}
      {error && result && result.generated_code && (
        <div className="mt-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            What was attempted
          </h2>
          <pre className="mt-3 overflow-x-auto rounded-md bg-gray-900 p-4 text-xs leading-relaxed text-gray-100">
            <code>{result.generated_code}</code>
          </pre>
        </div>
      )}

      {/* Coming soon — labelled NON-FUNCTIONAL stubs */}
      <section className="mt-12 border-t border-gray-200 pt-8">
        <div className="mb-4 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-gray-700">Coming soon</h2>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
            roadmap
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {/* Charts stub */}
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 opacity-70">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-500">Charts</p>
              <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                coming soon
              </span>
            </div>
            <div className="mt-3 flex h-20 items-center justify-center rounded-md border border-gray-200 bg-white text-xs text-gray-400">
              Chart will render here
            </div>
          </div>

          {/* Database connection stub */}
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 opacity-70">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-500">Connect a database</p>
              <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                coming soon
              </span>
            </div>
            <button
              type="button"
              disabled
              aria-disabled="true"
              className="mt-3 w-full cursor-not-allowed rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-400"
            >
              Connect…
            </button>
          </div>

          {/* Export stub */}
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 opacity-70">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-gray-500">Export results</p>
              <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                coming soon
              </span>
            </div>
            <button
              type="button"
              disabled
              aria-disabled="true"
              className="mt-3 w-full cursor-not-allowed rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-400"
            >
              Export
            </button>
          </div>
        </div>
      </section>
    </main>
  )
}
