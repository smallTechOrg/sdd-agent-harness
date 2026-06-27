'use client'

import { useRef, useState } from 'react'
import { Dataset, friendlyError } from './types'

interface Props {
  dataset: Dataset | null
  onUploaded: (dataset: Dataset) => void
}

export default function UploadPanel({ dataset, onUploaded }: Props) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function upload(file: File) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError("That doesn't look like a CSV — please choose a .csv file.")
      return
    }
    setUploading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/datasets', { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) {
        setError(friendlyError(body.detail?.code, body.detail?.message ?? `Upload failed (${res.status})`))
        return
      }
      onUploaded(body.data as Dataset)
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setUploading(false)
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) upload(file)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) upload(file)
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Data source</h2>

      <div
        onDragOver={e => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition ${
          dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
        } ${uploading ? 'cursor-wait opacity-60' : ''}`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={onFileChange}
          disabled={uploading}
        />
        {uploading ? (
          <p className="flex items-center gap-2 text-sm text-gray-600">
            <Spinner /> Uploading and profiling…
          </p>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-700">Drop a CSV here, or click to choose</p>
            <p className="mt-1 text-xs text-gray-400">Processed locally on this machine</p>
          </>
        )}
      </div>

      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {dataset && !uploading && (
        <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <p className="text-sm font-medium text-gray-800">{dataset.name}</p>
          <p className="text-xs text-gray-500">{dataset.row_count.toLocaleString()} rows</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {dataset.columns.map(col => (
              <span
                key={col.name}
                className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-xs text-gray-600 ring-1 ring-gray-200"
              >
                {col.name}
                <span className="text-gray-400">·{col.type}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-gray-500" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}
