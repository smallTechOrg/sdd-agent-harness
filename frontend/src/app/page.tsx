'use client'

import { useState } from 'react'
import PrivacyBadge from './components/PrivacyBadge'
import UploadPanel from './components/UploadPanel'
import ChatPanel from './components/ChatPanel'
import ComingSoon from './components/ComingSoon'
import { Dataset } from './components/types'

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">DataChat</h1>
        <p className="mt-1 text-sm text-gray-500">Upload a CSV and ask questions about it in plain English.</p>
      </header>

      <div className="mb-6">
        <PrivacyBadge />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-6">
          <UploadPanel dataset={dataset} onUploaded={setDataset} />
          <ComingSoon />
        </aside>

        <ChatPanel dataset={dataset} />
      </div>
    </main>
  )
}
