'use client'

import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
} from 'recharts'

type UploadState = 'idle' | 'uploading' | 'done' | 'error'

interface DatasetInfo {
  dataset_id: string
  filename: string
  columns: string[]
  row_count: number
}

interface AnalysisResult {
  question: string
  chart_type: string
  labels: string[]
  values: number[]
  summary: string
}

function ResultChart({
  chart_type,
  labels,
  values,
}: {
  chart_type: string
  labels: string[]
  values: number[]
}) {
  const data = labels.map((label, i) => ({ name: label, value: values[i] }))
  const scatterData = labels.map((l, i) => ({ x: i, y: values[i], name: l }))

  if (chart_type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (chart_type === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={350}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="x" name="Index" />
          <YAxis dataKey="y" name="Value" />
          <ZAxis range={[60, 60]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ payload }) => {
              if (payload && payload.length) {
                const pt = payload[0].payload as { x: number; y: number; name: string }
                return (
                  <div className="rounded bg-white px-2 py-1 text-xs shadow border border-gray-200">
                    <p className="font-medium">{pt.name}</p>
                    <p>Value: {pt.y}</p>
                  </div>
                )
              }
              return null
            }}
          />
          <Scatter data={scatterData} fill="#3b82f6" />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // default: bar
  return (
    <ResponsiveContainer width="100%" height={350}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="value" fill="#3b82f6" />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Home() {
  // file upload state
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dataset, setDataset] = useState<DatasetInfo | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  // chat state
  const [question, setQuestion] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [results, setResults] = useState<AnalysisResult[]>([])

  // modal state
  const [showDbModal, setShowDbModal] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File) {
    const allowed = ['.csv', '.xlsx', '.xls']
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!allowed.includes(ext)) {
      setUploadState('error')
      setUploadError(`File type "${ext}" is not supported. Please upload a CSV or Excel file.`)
      return
    }

    setUploadState('uploading')
    setUploadError(null)
    setDataset(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch('/datasets', {
        method: 'POST',
        body: formData,
      })
      const json = await res.json()
      if (!res.ok) {
        const msg =
          json?.detail?.message ??
          json?.error ??
          `Upload failed (${res.status})`
        setUploadState('error')
        setUploadError(msg)
      } else if (json?.error) {
        setUploadState('error')
        setUploadError(json.error)
      } else {
        setDataset(json.data)
        setUploadState('done')
      }
    } catch {
      setUploadState('error')
      setUploadError('Network error — is the server running?')
    }
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(false)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  async function handleAnalyze() {
    if (!dataset || !question.trim() || analyzing) return

    const q = question.trim()
    setAnalyzing(true)
    setAnalyzeError(null)

    try {
      const res = await fetch('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset_id: dataset.dataset_id, question: q }),
      })
      const json = await res.json()
      if (!res.ok) {
        const msg =
          json?.detail?.message ??
          json?.error ??
          `Analysis failed (${res.status})`
        setAnalyzeError(msg)
      } else if (json?.error) {
        setAnalyzeError(json.error)
      } else {
        const result: AnalysisResult = {
          question: q,
          chart_type: json.data.chart_type,
          labels: json.data.labels,
          values: json.data.values,
          summary: json.data.summary,
        }
        setResults(prev => [result, ...prev])
        setQuestion('')
      }
    } catch {
      setAnalyzeError('Network error — is the server running?')
    } finally {
      setAnalyzing(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleAnalyze()
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-gray-900">
          Data Analysis Agent
        </h1>
        <p className="mt-3 text-base text-gray-500">
          Upload a CSV or Excel file and ask questions in plain English — get instant charts and insights.
        </p>
      </div>

      {/* Data Source Panel */}
      <div className="mb-6 flex gap-3">
        <button
          className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          onClick={() => {
            setUploadState('idle')
            setDataset(null)
            setUploadError(null)
          }}
        >
          Upload File
        </button>
        <button
          className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-500 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-300 focus:ring-offset-2"
          onClick={() => setShowDbModal(true)}
        >
          Connect Database{' '}
          <span className="ml-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-400">
            Phase 2
          </span>
        </button>
      </div>

      {/* File Upload Area */}
      <div
        className={`mb-6 rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          isDragging
            ? 'border-blue-400 bg-blue-50'
            : uploadState === 'error'
            ? 'border-red-400 bg-red-50'
            : uploadState === 'done'
            ? 'border-green-400 bg-green-50'
            : 'border-gray-300 bg-white hover:border-gray-400'
        } cursor-pointer`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => {
          if (uploadState !== 'uploading') fileInputRef.current?.click()
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={handleInputChange}
        />

        {uploadState === 'idle' && (
          <>
            <div className="mb-3 flex justify-center">
              <svg
                className="h-10 w-10 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
            </div>
            <p className="text-sm text-gray-600">
              Drop your CSV or Excel file here, or{' '}
              <span className="font-medium text-blue-600">click to browse</span>
            </p>
            <p className="mt-1 text-xs text-gray-400">
              Supported: .csv, .xlsx, .xls
            </p>
          </>
        )}

        {uploadState === 'uploading' && (
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <p className="text-sm text-gray-600">
              Uploading{' '}
              <span className="font-medium">
                {fileInputRef.current?.files?.[0]?.name ?? 'file'}
              </span>
              ...
            </p>
          </div>
        )}

        {uploadState === 'done' && dataset && (
          <div className="flex flex-col items-center gap-2" onClick={e => e.stopPropagation()}>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-100">
              <svg
                className="h-5 w-5 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-800">{dataset.filename}</p>
            <p className="text-xs text-gray-500">
              Columns: {dataset.columns.join(', ')}
            </p>
            <p className="text-xs text-gray-500">{dataset.row_count} rows</p>
            <button
              className="mt-2 text-xs text-blue-500 underline"
              onClick={() => {
                setUploadState('idle')
                setDataset(null)
                setResults([])
                setAnalyzeError(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
            >
              Upload a different file
            </button>
          </div>
        )}

        {uploadState === 'error' && (
          <div className="flex flex-col items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
              <svg
                className="h-5 w-5 text-red-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <p className="text-sm font-medium text-red-700">Upload failed</p>
            <p className="text-xs text-red-600">{uploadError}</p>
            <button
              className="mt-2 text-xs text-blue-500 underline"
              onClick={e => {
                e.stopPropagation()
                setUploadState('idle')
                setUploadError(null)
                if (fileInputRef.current) fileInputRef.current.value = ''
              }}
            >
              Try again
            </button>
          </div>
        )}
      </div>

      {/* Chat Input — shown after successful upload */}
      {uploadState === 'done' && dataset && (
        <div className="mb-8 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <label
            htmlFor="question"
            className="mb-1.5 block text-sm font-medium text-gray-700"
          >
            Ask a question about your data
          </label>
          <textarea
            id="question"
            rows={3}
            className="w-full rounded-lg border border-gray-300 p-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            placeholder="Ask a question about your data…"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={analyzing}
          />

          {/* Example hints */}
          <div className="mt-2 flex flex-wrap gap-2">
            {['Show revenue by month', 'Compare sales by product', 'Plot trends over time'].map(
              hint => (
                <button
                  key={hint}
                  className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-500 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
                  onClick={() => setQuestion(hint)}
                  disabled={analyzing}
                >
                  {hint}
                </button>
              )
            )}
          </div>

          <div className="mt-3 flex items-center gap-3">
            <button
              className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              onClick={handleAnalyze}
              disabled={analyzing || !question.trim()}
            >
              {analyzing ? 'Analyzing...' : 'Analyze'}
            </button>
            {analyzing && (
              <span className="text-xs text-gray-500">
                Running analysis — this may take a moment…
              </span>
            )}
          </div>

          {analyzeError && (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {analyzeError}
            </div>
          )}
        </div>
      )}

      {/* Results Area */}
      <div>
        {results.length === 0 ? (
          <p className="text-center text-sm text-gray-400 py-8">
            Upload a file and ask a question to see results here.
          </p>
        ) : (
          <div className="space-y-6">
            {results.map((result, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
              >
                <h2 className="mb-4 text-base font-semibold text-gray-800">
                  {result.question}
                </h2>
                <ResultChart
                  chart_type={result.chart_type}
                  labels={result.labels}
                  values={result.values}
                />
                <p className="mt-4 text-sm text-gray-600">{result.summary}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Phase 2 Modal — Connect Database */}
      {showDbModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowDbModal(false)}
        >
          <div
            className="relative w-full max-w-md rounded-xl bg-white p-8 shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              className="absolute right-4 top-4 rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none"
              onClick={() => setShowDbModal(false)}
              aria-label="Close modal"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>

            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
              <svg className="h-6 w-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4"
                />
              </svg>
            </div>

            <h3 className="mb-2 text-lg font-semibold text-gray-900">
              Coming in Phase 2
            </h3>
            <p className="text-sm text-gray-500">
              PostgreSQL database connection will be available in Phase 2. Stay tuned!
            </p>

            <button
              className="mt-6 w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              onClick={() => setShowDbModal(false)}
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
