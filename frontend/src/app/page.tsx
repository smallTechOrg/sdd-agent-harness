'use client'

import { useState } from 'react'
import { UploadZone } from './components/UploadZone'
import { QuestionInput } from './components/QuestionInput'
import { ResultView } from './components/ResultView'
import { HistoryStub } from './components/HistoryStub'
import { runAnalysis, type Analysis, type Dataset } from './components/api'

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  function handleUploaded(next: Dataset) {
    setDataset(next)
    // a new dataset invalidates the previous result
    setAnalysis(null)
    setAnalysisError(null)
  }

  async function handleAsk(question: string) {
    if (!dataset) return
    setAnalyzing(true)
    setAnalysisError(null)
    setAnalysis(null)
    try {
      const result = await runAnalysis(dataset.dataset_id, question)
      setAnalysis(result)
    } catch (err) {
      setAnalysisError(
        err instanceof Error ? err.message : 'The analysis could not be run. Please try again.',
      )
    } finally {
      setAnalyzing(false)
    }
  }

  const datasetReady = dataset?.status === 'ready'

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Data Analysis Agent</h1>
        <p className="mt-1 text-base text-slate-600">
          Ask questions about your data — answers computed locally, with the code shown.
        </p>
      </header>

      <div className="space-y-6">
        <UploadZone dataset={dataset} onUploaded={handleUploaded} />

        <QuestionInput enabled={!!datasetReady} loading={analyzing} onAsk={handleAsk} />

        <ResultView analysis={analysis} loading={analyzing} error={analysisError} />

        <HistoryStub />
      </div>

      <footer className="mt-10 text-center text-xs text-slate-400">
        Your raw data never leaves this machine — only the schema and a small sample are sent to the model.
      </footer>
    </main>
  )
}
