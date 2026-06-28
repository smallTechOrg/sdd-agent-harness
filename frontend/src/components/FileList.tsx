'use client'
import { useState, useRef, useCallback } from 'react'
import { UploadedFileInfo } from '@/types'
import ProfilePanel from '@/components/ProfilePanel'

interface Props {
  files: UploadedFileInfo[]
  selectedFileId: string | null
  onFileSelect: (id: string) => void
  onUploadComplete: (file: UploadedFileInfo) => void
}

export default function FileList({ files, selectedFileId, onFileSelect, onUploadComplete }: Props) {
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [lastUploaded, setLastUploaded] = useState<UploadedFileInfo | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/files/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail?.message || `Upload failed (${res.status})`)
      }
      const data = await res.json()
      const uploaded: UploadedFileInfo = {
        file_id: data.file_id,
        original_filename: data.original_filename,
        profile: data.profile,
        row_count: data.profile.row_count,
        column_count: data.profile.column_count,
      }
      setLastUploaded(uploaded)
      onUploadComplete(uploaded)
      onFileSelect(uploaded.file_id)
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [onUploadComplete, onFileSelect])

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleUpload}
          data-testid="file-input"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium py-2 px-3 rounded-md transition-colors"
          data-testid="upload-btn"
        >
          {uploading ? 'Uploading…' : '+ Upload CSV'}
        </button>
        {uploadError && (
          <p className="mt-2 text-xs text-red-600" role="alert">{uploadError}</p>
        )}
      </div>

      {lastUploaded?.profile && (
        <div className="px-4">
          <ProfilePanel profile={lastUploaded.profile} filename={lastUploaded.original_filename} />
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3">
        {files.length === 0 ? (
          <p className="text-xs text-gray-400 text-center mt-4">No files yet. Upload a CSV to start.</p>
        ) : (
          <ul className="space-y-1">
            {files.map((f) => (
              <li key={f.file_id}>
                <button
                  onClick={() => onFileSelect(f.file_id)}
                  className={`w-full text-left p-2 rounded text-sm truncate transition-colors ${
                    selectedFileId === f.file_id
                      ? 'bg-indigo-100 text-indigo-800 font-medium'
                      : 'hover:bg-gray-100 text-gray-700'
                  }`}
                  title={f.original_filename}
                  data-testid={`file-item-${f.file_id}`}
                >
                  <span className="block truncate">{f.original_filename}</span>
                  <span className="text-xs text-gray-400">{f.row_count?.toLocaleString() ?? '?'} rows</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* STUB: Multi-file operations */}
      <div className="p-4 border-t border-gray-100">
        <div className="bg-gray-50 border border-dashed border-gray-300 rounded p-3 text-center">
          <p className="text-xs text-gray-400 font-medium">Multi-file join</p>
          <p className="text-xs text-gray-400">Coming in Phase 2</p>
        </div>
      </div>
    </div>
  )
}
