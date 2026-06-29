'use client'

import { useRef, useState } from 'react'
import { uploadDataset, type Dataset } from '@/lib/api'

export function UploadPanel({
  dataset,
  onUploaded,
}: {
  dataset: Dataset | null
  onUploaded: (d: Dataset) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleUpload() {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const d = await uploadDataset(file)
      onUploaded(d)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section
      data-testid="upload-panel"
      className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-gray-800">1 · Upload a CSV</h2>
      <p className="mt-1 text-xs text-gray-500">
        Your data is crunched locally — only the schema and result rows are sent to the model.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          data-testid="file-input"
          onChange={e => {
            setFile(e.target.files?.[0] ?? null)
            setError(null)
          }}
          disabled={loading}
          className="block text-sm text-gray-600 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-gray-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-gray-700 hover:file:bg-gray-200"
        />
        <button
          type="button"
          onClick={handleUpload}
          disabled={loading || !file}
          data-testid="upload-button"
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden />
          )}
          {loading ? 'Uploading…' : 'Upload CSV'}
        </button>
      </div>

      {error && (
        <div
          data-testid="upload-error"
          role="alert"
          className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {dataset && (
        <div
          data-testid="dataset-summary"
          className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/60 p-4"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium text-gray-900" data-testid="dataset-name">
              {dataset.name}
            </span>
            <span className="text-sm text-emerald-700" data-testid="dataset-rowcount">
              {dataset.row_count.toLocaleString()} rows · {dataset.schema.length} columns
            </span>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5" data-testid="dataset-columns">
            {dataset.schema.map(col => (
              <span
                key={col.name}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-2 py-1 text-xs"
              >
                <span className="font-medium text-gray-800">{col.name}</span>
                <span className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[10px] uppercase text-gray-500">
                  {col.type}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
