'use client'

import { useState } from 'react'
import { UploadPanel } from '../components/UploadPanel'
import type { UploadSession } from '../components/UploadPanel'
import { ChatPanel } from '../components/ChatPanel'

export default function Home() {
  const [uploadedSession, setUploadedSession] = useState<UploadSession | null>(null)

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-col md:flex-row gap-6 h-[calc(100vh-120px)]">
        {/* Upload Panel — left/top */}
        <div className="md:w-80 flex-shrink-0 rounded-xl border border-gray-200 bg-white p-5 shadow-sm overflow-y-auto">
          <UploadPanel onUploadSuccess={(session) => setUploadedSession(session)} />
        </div>

        {/* Chat Panel — right/bottom */}
        <div className="flex-1 rounded-xl border border-gray-200 bg-white p-5 shadow-sm flex flex-col min-h-0">
          <ChatPanel session={uploadedSession} />
        </div>
      </div>
    </main>
  )
}
