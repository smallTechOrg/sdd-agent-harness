'use client'

import { useRef, useState, type DragEvent, type ChangeEvent } from 'react'

interface UploadedFileInfo {
  table_name: string
  row_count: number
  columns: string[]
  filename: string
}

interface FileDropZoneProps {
  sessionId: string
  onFileUploaded: (info: UploadedFileInfo) => void
  disabled?: boolean
}

const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx', '.xls']
const MAX_SIZE_MB = 50
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024

function getExtension(name: string): string {
  const idx = name.lastIndexOf('.')
  return idx >= 0 ? name.slice(idx).toLowerCase() : ''
}

export default function FileDropZone({ sessionId, onFileUploaded, disabled = false }: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const uploadFile = async (file: File) => {
    setError(null)
    const ext = getExtension(file.name)
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type "${ext}". Please upload a .csv, .xlsx, or .xls file.`)
      return
    }
    if (file.size > MAX_SIZE_BYTES) {
      setError(`File too large (max ${MAX_SIZE_MB} MB)`)
      return
    }

    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`/sessions/${sessionId}/files`, {
        method: 'POST',
        body: form,
      })
      const json = await res.json()
      if (!res.ok || !json.ok) {
        const msg = json?.error?.message ?? `Upload failed (${res.status})`
        setError(msg)
        return
      }
      onFileUploaded({
        table_name: json.data.table_name,
        row_count: json.data.row_count,
        columns: json.data.columns ?? [],
        filename: file.name,
      })
    } catch {
      setError('Network error — is the server running?')
    } finally {
      setUploading(false)
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (!disabled && !uploading) setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    if (disabled || uploading) return
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
    // Reset input so the same file can be re-uploaded
    e.target.value = ''
  }

  const handleClick = () => {
    if (!disabled && !uploading) inputRef.current?.click()
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled || uploading ? -1 : 0}
        aria-label="File upload zone"
        onClick={handleClick}
        onKeyDown={(e) => e.key === 'Enter' && handleClick()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={[
          'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors',
          dragging ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300 bg-white hover:border-indigo-300 hover:bg-gray-50',
          (disabled || uploading) ? 'cursor-not-allowed opacity-60' : '',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={handleChange}
          disabled={disabled || uploading}
        />

        {uploading ? (
          <>
            <svg
              className="h-6 w-6 animate-spin text-indigo-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
            </svg>
            <p className="text-sm font-medium text-indigo-600">Uploading...</p>
          </>
        ) : (
          <>
            <svg
              className="h-8 w-8 text-gray-400"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
              />
            </svg>
            <p className="text-sm font-medium text-gray-700">Drop CSV or Excel file here</p>
            <p className="text-xs text-gray-400">or click to browse</p>
          </>
        )}
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
