'use client'

import { useRef, useState } from 'react'

interface UploadCardProps {
  onFile: (file: File) => void
  loading: boolean
  loadingFilename: string | null
  error: string | null
}

export function UploadCard({
  onFile,
  loading,
  loadingFilename,
  error,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    onFile(files[0])
  }

  if (loading) {
    return (
      <section
        aria-label="Upload"
        className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="flex items-center gap-4">
          <span
            className="h-6 w-6 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600"
            aria-hidden="true"
          />
          <p className="text-base text-slate-700" data-testid="profiling-status">
            Profiling{' '}
            <span className="font-semibold">{loadingFilename}</span>… reading the
            full file and computing column stats.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section aria-label="Upload" className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={`rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          dragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-slate-300 bg-white hover:border-indigo-400'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="sr-only"
          data-testid="file-input"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-6 w-6"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0L8 8m4-4 4 4" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
        </div>
        <p className="text-base font-medium text-slate-800">
          Drop a CSV or Excel file here, or
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-3 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
        >
          Choose a file
        </button>
        <p className="mt-3 text-sm text-slate-500">
          .csv or .xlsx, up to ~100MB. Your rows stay on this machine.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
          data-testid="upload-error"
        >
          <span className="font-semibold">Couldn&apos;t read that file. </span>
          {error}
        </div>
      )}
    </section>
  )
}
