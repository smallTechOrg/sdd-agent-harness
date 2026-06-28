'use client'

import { useRef, useState } from 'react'
import { uploadDataset, ApiError, NetworkError, type UploadResponse } from '@/lib/api'
import { ComingSoonBadge } from './Stub'

interface EmptyStateProps {
  onUploaded: (result: UploadResponse) => void
}

const EXCEL_STUB_MESSAGE =
  'Excel (.xlsx) and multi-sheet workbooks are coming in a later phase. For now, please upload a .csv file.'

/**
 * First-run empty state — REAL.
 * A large centered CSV dropzone/button. `.csv` uploads via POST /api/datasets;
 * `.xlsx` is intercepted client-side and shows the labelled Excel stub message
 * (it is NOT uploaded). Upload errors render inline on the dropzone with the
 * real server message.
 */
export default function EmptyState({ onUploaded }: EmptyStateProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [excelNotice, setExcelNotice] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    setExcelNotice(false)

    const lower = file.name.toLowerCase()
    if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) {
      // Labelled Excel stub — do NOT upload.
      setExcelNotice(true)
      return
    }
    if (!lower.endsWith('.csv')) {
      setError('Only .csv files are supported right now.')
      return
    }

    setUploading(true)
    try {
      const result = await uploadDataset(file)
      onUploaded(result)
    } catch (err) {
      if (err instanceof ApiError || err instanceof NetworkError) {
        setError(err.message)
      } else {
        setError('Upload failed unexpectedly.')
      }
    } finally {
      setUploading(false)
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) void handleFile(file)
    e.target.value = '' // allow re-selecting the same file
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) void handleFile(file)
  }

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-12">
      <div className="w-full max-w-xl text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
          Upload a CSV to start
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-gray-500">
          Your data stays on this machine — only the column names and a few sample
          rows are sent to the model.
        </p>

        {/* Dropzone — REAL */}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          disabled={uploading}
          className={`mt-6 flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 transition ${
            dragOver
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-300 bg-white hover:border-blue-300 hover:bg-gray-50'
          } ${uploading ? 'cursor-wait opacity-70' : 'cursor-pointer'}`}
        >
          <svg
            className="mb-3 h-10 w-10 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
            />
          </svg>
          <span className="text-sm font-medium text-gray-700">
            {uploading ? 'Uploading & profiling…' : 'Drag a .csv here or click to choose'}
          </span>
          <span className="mt-1 text-xs text-gray-400">.csv files only</span>
        </button>

        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={onInputChange}
        />

        {/* Upload error — inline with the real server message */}
        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {/* Labelled Excel stub message (Phase 4) */}
        {excelNotice && (
          <div
            role="status"
            className="mt-4 flex items-start gap-3 rounded-lg border border-dashed border-amber-300 bg-amber-50 px-4 py-3 text-left"
          >
            <span className="mt-0.5">
              <ComingSoonBadge phase="P4" />
            </span>
            <p className="text-sm text-amber-800">{EXCEL_STUB_MESSAGE}</p>
          </div>
        )}

        {/* Faint preview of the workbench layout — labelled "appears after upload" */}
        <div className="mt-10 select-none" aria-hidden>
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-400">
            Workbench preview — appears after upload
          </p>
          <div className="grid grid-cols-[1fr_2fr_1.4fr] gap-2 opacity-40">
            <div className="h-24 rounded-md border border-dashed border-gray-300 bg-gray-50" />
            <div className="h-24 rounded-md border border-dashed border-gray-300 bg-gray-50" />
            <div className="h-24 rounded-md border border-dashed border-gray-300 bg-gray-50" />
          </div>
        </div>
      </div>
    </div>
  )
}
