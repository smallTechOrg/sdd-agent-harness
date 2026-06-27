'use client'

import { useRef, useState } from 'react'

import { uploadDataset } from '@/lib/api'
import type { Dataset } from '@/lib/types'

interface Props {
  dataset: Dataset | null
  onUploaded: (dataset: Dataset) => void
}

const ACCEPT = '.csv,.xlsx'

export default function UploadDropzone({ dataset, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFile(file: File) {
    setUploading(true)
    setError(null)
    try {
      const ds = await uploadDataset(file)
      onUploaded(ds)
    } catch (e) {
      const message =
        e instanceof Error
          ? e.message
          : "Couldn't read that file — please upload a CSV or .xlsx"
      // Network failures throw a TypeError with no useful message.
      setError(
        message && !message.startsWith('Failed to fetch')
          ? message
          : 'Network error — is the server running?',
      )
    } finally {
      setUploading(false)
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void handleFile(file)
  }

  return (
    <section aria-label="Upload dataset">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={e => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={uploading}
        className={[
          'flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition',
          dragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50/40',
          uploading ? 'cursor-wait opacity-70' : 'cursor-pointer',
        ].join(' ')}
      >
        {uploading ? (
          <span className="inline-flex items-center gap-2 text-sm text-gray-600">
            <Spinner />
            Reading your file…
          </span>
        ) : (
          <>
            <span className="text-2xl" aria-hidden>
              ⬆️
            </span>
            <span className="mt-2 text-sm font-medium text-gray-700">
              {dataset ? 'Replace dataset' : 'Drop a CSV or Excel file'}
            </span>
            <span className="mt-1 text-xs text-gray-500">
              or click to browse (.csv, .xlsx)
            </span>
          </>
        )}
      </button>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) void handleFile(file)
          e.target.value = '' // allow re-uploading the same file
        }}
      />

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {error}
        </p>
      )}

      {dataset && !uploading && <SchemaPanel dataset={dataset} />}
    </section>
  )
}

function SchemaPanel({ dataset }: { dataset: Dataset }) {
  return (
    <div className="mt-4 rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium text-gray-800" title={dataset.filename}>
          {dataset.filename}
        </p>
        <span className="shrink-0 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium uppercase text-blue-600">
          {dataset.file_type}
        </span>
      </div>
      <p className="mt-1 text-xs text-gray-500">
        {dataset.row_count.toLocaleString()} rows ·{' '}
        {dataset.schema.columns.length} columns
      </p>

      <p className="mt-3 mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
        Detected schema
      </p>
      <ul className="space-y-1">
        {dataset.schema.columns.map(col => (
          <li
            key={col.name}
            className="flex items-center justify-between gap-2 rounded-md bg-gray-50 px-2 py-1 text-xs"
          >
            <span className="truncate font-mono text-gray-700" title={col.name}>
              {col.name}
            </span>
            <span className="shrink-0 font-mono text-gray-400">{col.dtype}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Spinner() {
  return (
    <span
      className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 motion-reduce:animate-none"
      aria-hidden
    />
  )
}
