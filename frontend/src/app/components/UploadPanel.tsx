'use client'

import { useRef, useState } from 'react'
import { uploadDataset } from '../lib/api'
import ErrorBanner from './ErrorBanner'
import Spinner from './Spinner'

interface UploadPanelProps {
  onUploaded: () => void
}

export default function UploadPanel({ onUploaded }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleUpload() {
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await uploadDataset(file)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onUploaded()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2">
        <label htmlFor="file-upload" className="text-sm font-medium text-gray-700">
          Upload a dataset
        </label>
        <input
          id="file-upload"
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          disabled={uploading}
          onChange={e => setFile(e.target.files?.[0] ?? null)}
          className="block w-full cursor-pointer rounded-lg border border-gray-300 text-sm file:mr-3 file:cursor-pointer file:border-0 file:bg-gray-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-gray-700 hover:file:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <button
        type="button"
        onClick={handleUpload}
        disabled={uploading || !file}
        className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? <Spinner label="Uploading…" /> : 'Upload'}
      </button>
      <p className="text-xs text-gray-500">Accepted formats: .csv, .xlsx</p>
      {error && <ErrorBanner message={error} />}
    </div>
  )
}
