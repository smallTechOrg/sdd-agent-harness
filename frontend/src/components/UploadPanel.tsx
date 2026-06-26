'use client'

import { useRef, useState } from 'react'

export interface UploadSession {
  session_id: string
  table_name: string
  schema: Array<{ column: string; type: string }>
}

interface UploadPanelProps {
  onUploadSuccess: (session: UploadSession) => void
}

export function UploadPanel({ onUploadSuccess }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadedSession, setUploadedSession] = useState<UploadSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    setSelectedFile(file)
    setError(null)
    setUploadedSession(null)
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0] ?? null
    if (file && !file.name.endsWith('.csv')) {
      setError('Please drop a .csv file.')
      return
    }
    setSelectedFile(file)
    setError(null)
    setUploadedSession(null)
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
  }

  async function handleUpload() {
    if (!selectedFile) return
    setUploading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      const res = await fetch('/upload', { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) {
        const msg =
          data.detail?.message ??
          data.error?.message ??
          `Upload failed (${res.status})`
        setError(msg)
        return
      }
      if (!data.ok) {
        const msg =
          data.error?.message ??
          data.detail?.message ??
          'Upload failed.'
        setError(msg)
        return
      }
      const session: UploadSession = {
        session_id: data.data.session_id,
        table_name: data.data.table_name,
        schema: data.data.schema,
      }
      setUploadedSession(session)
      onUploadSuccess(session)
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-base font-semibold text-gray-800">Upload CSV</h2>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => inputRef.current?.click()}
        className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-6 py-8 cursor-pointer hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
      >
        <svg
          className="h-8 w-8 text-gray-400"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="text-sm text-gray-500">
          {selectedFile ? (
            <span className="font-medium text-indigo-600">{selectedFile.name}</span>
          ) : (
            <>
              <span className="font-medium text-indigo-600">Choose a file</span> or drag and drop
            </>
          )}
        </p>
        <p className="text-xs text-gray-400">CSV files only</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {/* Upload button */}
      <button
        type="button"
        onClick={handleUpload}
        disabled={!selectedFile || uploading}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {uploading ? 'Uploading…' : 'Upload'}
      </button>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Schema preview */}
      {uploadedSession && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-green-700 mb-2">
            Loaded: {uploadedSession.table_name}
          </p>
          <ul className="divide-y divide-green-100">
            {uploadedSession.schema.map((col) => (
              <li key={col.column} className="flex items-center justify-between py-1 text-xs text-green-800">
                <span className="font-mono">{col.column}</span>
                <span className="text-green-600 bg-green-100 px-1.5 py-0.5 rounded">{col.type}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Join another file stub */}
      <div className="mt-1">
        <button
          type="button"
          className="text-xs text-gray-400 cursor-not-allowed underline-offset-2"
          title="Coming in Phase 3"
          onClick={() =>
            alert('Coming soon — multi-file join support is planned for Phase 3')
          }
        >
          Join another file
          <span className="ml-1 text-xs bg-gray-100 text-gray-400 px-1.5 py-0.5 rounded border border-gray-200">
            Phase 3
          </span>
        </button>
      </div>
    </div>
  )
}
