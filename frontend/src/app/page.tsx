'use client'

import { useState } from 'react'
import { askQuestion, type AskResult, type Dataset } from '@/lib/api'
import { UploadPanel } from '@/components/UploadPanel'
import { ProfilePanel } from '@/components/ProfilePanel'
import { QuestionPanel } from '@/components/QuestionPanel'
import { AnswerPanel } from '@/components/AnswerPanel'
import { ComingSoonCard } from '@/components/ComingSoon'

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [asking, setAsking] = useState(false)
  const [result, setResult] = useState<AskResult | null>(null)
  const [askError, setAskError] = useState<string | null>(null)

  function handleUploaded(d: Dataset) {
    setDataset(d)
    setResult(null)
    setAskError(null)
  }

  async function handleAsk(question: string) {
    if (!dataset) return
    setAsking(true)
    setAskError(null)
    setResult(null)
    try {
      const res = await askQuestion(dataset.id, question)
      setResult(res)
    } catch (e) {
      setAskError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setAsking(false)
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">Local Data Analyst</h1>
        <p className="mt-1 text-sm text-gray-500">
          Ask plain-English questions about your data and see the exact SQL behind every number — computed locally, your raw rows never leave the machine.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
        {/* Core, REAL path */}
        <div className="space-y-6">
          <UploadPanel dataset={dataset} onUploaded={handleUploaded} />
          {dataset?.profile && dataset.profile.length > 0 && (
            <ProfilePanel profile={dataset.profile} />
          )}
          <QuestionPanel enabled={!!dataset} loading={asking} onAsk={handleAsk} />
          <AnswerPanel
            loading={asking}
            result={result}
            error={askError}
            onFollowup={handleAsk}
          />
        </div>

        {/* Coming-soon stubs — visible, designed, clearly labelled (never bugs) */}
        <aside className="space-y-4" data-testid="coming-soon-stubs">
          <ComingSoonCard
            title="Datasets"
            icon="🗂"
            phase="Phase 3"
            description="Load and multi-select several datasets to compare and join them in one query."
          />
          <ComingSoonCard
            title="Cost meter"
            icon="💰"
            phase="Phase 3"
            description="Per-query token usage and estimated cost, with an expensive-query warning."
          />
          <ComingSoonCard
            title="History & audit trail"
            icon="📜"
            phase="Phase 3"
            description="Browse every past question with its SQL, result, and timestamp."
          />
          <ComingSoonCard
            title="Live step stream"
            icon="📡"
            phase="Phase 3"
            description="Watch the agent generate SQL, run it, and answer — step by step, live."
          />
        </aside>
      </div>
    </main>
  )
}
