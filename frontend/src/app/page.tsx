'use client'
import { useState, useEffect } from 'react'
import FileList from '@/components/FileList'
import ChatPanel from '@/components/ChatPanel'
import { UploadedFileInfo } from '@/types'

export default function Home() {
  const [files, setFiles] = useState<UploadedFileInfo[]>([])
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null)

  // Load existing files on mount
  useEffect(() => {
    fetch('/api/files')
      .then((r) => r.json())
      .then((data) => {
        if (data.files) setFiles(data.files.map((f: {
          file_id: string
          original_filename: string
          row_count: number
          column_count: number
          file_size_bytes?: number
          created_at?: string
        }) => ({
          file_id: f.file_id,
          original_filename: f.original_filename,
          row_count: f.row_count,
          column_count: f.column_count,
          file_size_bytes: f.file_size_bytes,
          created_at: f.created_at,
        })))
      })
      .catch(() => {})
  }, [])

  const handleUploadComplete = (file: UploadedFileInfo) => {
    setFiles((prev) => {
      if (prev.find((f) => f.file_id === file.file_id)) return prev
      return [file, ...prev]
    })
  }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Left sidebar */}
      <aside className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <h1 className="text-base font-bold text-gray-900">Data Analysis Agent</h1>
          <p className="text-xs text-gray-500 mt-0.5">Upload CSVs and ask questions</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          <FileList
            files={files}
            selectedFileId={selectedFileId}
            onFileSelect={setSelectedFileId}
            onUploadComplete={handleUploadComplete}
          />
        </div>
      </aside>

      {/* Main panel */}
      <main className="flex-1 flex flex-col min-w-0">
        <ChatPanel selectedFileId={selectedFileId} />
      </main>
    </div>
  )
}
