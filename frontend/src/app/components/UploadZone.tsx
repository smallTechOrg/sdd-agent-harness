'use client'

import { useId, useRef, useState } from 'react'
import { ComingSoon } from './ComingSoon'
import { uploadDataset, type Dataset } from './api'

const numberFmt = new Intl.NumberFormat()

export function UploadZone({
  dataset,
  onUploaded,
}: {
  dataset: Dataset | null
  onUploaded: (dataset: Dataset) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInputId = useId()

  async function handleFile(file: File) {
    setError(null)
    setUploading(true)
    try {
      const result = await uploadDataset(file)
      onUploaded(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) void handleFile(file)
    // allow re-selecting the same file later
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (uploading) return
    const file = e.dataTransfer.files?.[0]
    if (file) void handleFile(file)
  }

  return (
    <section
      aria-labelledby="upload-heading"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white"
        >
          1
        </span>
        <h2 id="upload-heading" className="text-lg font-semibold text-slate-900">
          Upload your data
        </h2>
      </div>

      <input
        ref={inputRef}
        id={fileInputId}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        onChange={onInputChange}
        disabled={uploading}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          if (!uploading) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={uploading}
        className={`mt-4 flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${
          dragging
            ? 'border-indigo-400 bg-indigo-50'
            : 'border-slate-300 bg-slate-50 hover:border-indigo-300 hover:bg-indigo-50/40'
        }`}
      >
        {uploading ? (
          <>
            <Spinner />
            <span className="text-sm font-medium text-slate-700">Uploading and profiling…</span>
          </>
        ) : (
          <>
            <UploadIcon />
            <span className="text-sm font-medium text-slate-700">
              Drag &amp; drop a CSV file, or <span className="text-indigo-600">browse</span>
            </span>
            <span className="text-xs text-slate-500">CSV files up to a few thousand rows</span>
          </>
        )}
      </button>

      {/* Format options — CSV is real; Excel is a labelled Phase 2 stub. */}
      <fieldset className="mt-4">
        <legend className="sr-only">File format</legend>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="inline-flex items-center gap-2 text-slate-700">
            <input type="radio" name="format" defaultChecked readOnly className="accent-indigo-600" />
            CSV
          </label>
          <label className="inline-flex cursor-not-allowed items-center gap-2 text-slate-400">
            <input type="radio" name="format" disabled className="accent-slate-400" />
            Excel .xlsx
            <ComingSoon />
          </label>
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {dataset && !error && (
        <p
          role="status"
          className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
        >
          <CheckIcon />
          <span className="font-medium">{dataset.filename}</span>
          <span className="text-emerald-700">
            · {numberFmt.format(dataset.row_count)} rows × {numberFmt.format(dataset.column_count)} cols
          </span>
          <span aria-hidden>✓</span>
        </p>
      )}
    </section>
  )
}

function Spinner() {
  return (
    <svg
      className="h-6 w-6 animate-spin text-indigo-600"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  )
}

function UploadIcon() {
  return (
    <svg className="h-8 w-8 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="h-4 w-4 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  )
}
