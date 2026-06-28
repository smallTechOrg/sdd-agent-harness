'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  getDataset,
  getHistory,
  ApiError,
  NetworkError,
  type DatasetProfile,
  type ThreadMessage,
  type HistoryItem,
  type UploadResponse,
} from '@/lib/api'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import EmptyState from './components/EmptyState'
import ChatPanel from './components/ChatPanel'
import ProfilePanel from './components/ProfilePanel'

interface ActiveDataset {
  id: string
  name: string
  profile: DatasetProfile
  messages: ThreadMessage[]
}

export default function Home() {
  const [dataset, setDataset] = useState<ActiveDataset | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  // After an upload, load the dataset (profile is already in the upload
  // response; the thread starts empty) and fetch any existing history.
  const handleUploaded = useCallback(async (result: UploadResponse) => {
    setLoadError(null)
    setDataset({
      id: result.dataset_id,
      name: result.name,
      profile: result.profile,
      messages: [],
    })
    try {
      const items = await getHistory(result.dataset_id)
      setHistory(items)
    } catch {
      // History is non-fatal on first upload — it is simply empty.
      setHistory([])
    }
  }, [])

  // Refresh the dataset thread + history after a run completes.
  const refreshHistory = useCallback(async () => {
    if (!dataset) return
    try {
      const [detail, items] = await Promise.all([
        getDataset(dataset.id),
        getHistory(dataset.id),
      ])
      setDataset((prev) =>
        prev && prev.id === detail.dataset_id
          ? { ...prev, profile: detail.profile, messages: detail.messages }
          : prev,
      )
      setHistory(items)
    } catch (err) {
      // A failed refresh should not wipe the live thread; surface quietly.
      if (err instanceof ApiError || err instanceof NetworkError) {
        setLoadError(err.message)
      }
    }
  }, [dataset])

  // Clear a transient load error after a moment.
  useEffect(() => {
    if (!loadError) return
    const t = setTimeout(() => setLoadError(null), 6000)
    return () => clearTimeout(t)
  }, [loadError])

  const sampleRowCount = dataset?.profile.sample_rows.length ?? 0

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header datasetName={dataset?.name} />

      {!dataset ? (
        <main className="flex flex-1 overflow-hidden">
          <Sidebar />
          <EmptyState onUploaded={(r) => void handleUploaded(r)} />
        </main>
      ) : (
        <main className="flex flex-1 overflow-hidden">
          <Sidebar datasetName={dataset.name} rowCount={dataset.profile.row_count} />

          <ChatPanel
            key={dataset.id}
            datasetId={dataset.id}
            profile={dataset.profile}
            initialMessages={dataset.messages}
            onRunComplete={() => void refreshHistory()}
          />

          <ProfilePanel
            profile={dataset.profile}
            history={history}
            sampleRowCount={sampleRowCount}
          />
        </main>
      )}

      {loadError && (
        <div
          role="alert"
          className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 shadow-lg"
        >
          {loadError}
        </div>
      )}
    </div>
  )
}
