'use client'

import { useEffect, useRef, useState } from 'react'
import { askQuestion, fetchCostToday, uploadDataset } from '../lib/api'
import type {
  AnswerEvent,
  DatasetResponse,
  ErrorEvent,
  StepEvent,
} from '../lib/types'
import { AnswerPanel } from '../components/AnswerPanel'
import { AskBox } from '../components/AskBox'
import { ProfileCard } from '../components/ProfileCard'
import { StepTrace } from '../components/StepTrace'
import { StuckPanel } from '../components/StuckPanel'
import { HistoryStub, MultiFileStub } from '../components/StubPanels'
import { UploadCard } from '../components/UploadCard'

export default function Home() {
  // Upload / profile state
  const [dataset, setDataset] = useState<DatasetResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadingName, setUploadingName] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  // Ask / answer state
  const [question, setQuestion] = useState('')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<StepEvent[]>([])
  const [answer, setAnswer] = useState<AnswerEvent | null>(null)
  const [stuck, setStuck] = useState<ErrorEvent | null>(null)

  // Daily cost badge
  const [dailyTotal, setDailyTotal] = useState<number>(0)

  // The ONE abort controller, owned for the component's whole lifetime. It is
  // created lazily on first ask and aborted ONLY when the component unmounts —
  // never on a re-render. setSteps/setRunning fire many re-renders while the
  // stream is live; none of them must tear the stream down, so the cleanup that
  // aborts has empty deps and runs only on unmount.
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    fetchCostToday().then((c) => {
      if (c) setDailyTotal(c.total_usd)
    })
  }, [])

  async function handleFile(file: File) {
    setUploading(true)
    setUploadingName(file.name)
    setUploadError(null)
    setDataset(null)
    setAnswer(null)
    setStuck(null)
    setSteps([])
    try {
      const ds = await uploadDataset(file)
      setDataset(ds)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Unknown error.')
    } finally {
      setUploading(false)
      setUploadingName(null)
    }
  }

  async function handleAsk() {
    if (!dataset || !question.trim() || running) return
    setRunning(true)
    setSteps([])
    setAnswer(null)
    setStuck(null)

    // One controller for this run, kept in a ref. It is NOT recreated on the
    // re-renders that setSteps/setRunning trigger, and it is only aborted on
    // unmount (see the mount effect above) — so the live stream survives every
    // state update fired while steps/answer arrive.
    const controller = new AbortController()
    abortRef.current = controller

    // Guard every state update so a run that finishes after unmount can't write.
    const guard =
      <T,>(fn: (v: T) => void) =>
      (v: T) => {
        if (mountedRef.current) fn(v)
      }

    try {
      await askQuestion(
        dataset.dataset_id,
        question.trim(),
        {
          onStep: guard((s: StepEvent) => setSteps((prev) => [...prev, s])),
          onAnswer: guard((a: AnswerEvent) => {
            setAnswer(a)
            setDailyTotal(a.daily_total_usd)
          }),
          onError: guard((err: ErrorEvent) => setStuck(err)),
        },
        controller.signal,
      )
    } catch (e) {
      // askQuestion surfaces its own errors via onError; this only fires for an
      // unexpected throw. Never leave the UI silently stuck.
      if (mountedRef.current) {
        setStuck({
          message:
            e instanceof Error && e.name === 'AbortError'
              ? 'The request was cancelled.'
              : 'Lost the connection while processing — is the server still running?',
          status: 'stuck',
        })
      }
    } finally {
      if (mountedRef.current) setRunning(false)
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  const showResultsPlaceholder =
    dataset && !running && !answer && !stuck && steps.length === 0

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      {/* Header */}
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Pandora
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Private CSV analysis. Your data stays on this machine — only schema
            and computed results reach the model.
          </p>
        </div>
        <div
          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm"
          data-testid="daily-cost-badge"
        >
          Today: ${dailyTotal.toFixed(4)}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
        {/* Main column */}
        <div className="space-y-6">
          <UploadCard
            onFile={handleFile}
            loading={uploading}
            loadingFilename={uploadingName}
            error={uploadError}
          />

          {dataset && (
            <>
              <ProfileCard
                dataset={dataset}
                onPickQuestion={(q) => setQuestion(q)}
              />

              <AskBox
                value={question}
                onChange={setQuestion}
                onSubmit={handleAsk}
                running={running}
              />

              {(running || steps.length > 0) && !answer && !stuck && (
                <StepTrace steps={steps} active={running} />
              )}

              {answer && <AnswerPanel answer={answer} steps={steps} />}

              {stuck && <StuckPanel error={stuck} />}

              {showResultsPlaceholder && (
                <div
                  className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-400"
                  data-testid="results-placeholder"
                >
                  Results will appear here once you ask a question.
                </div>
              )}

              <MultiFileStub />
            </>
          )}

          {!dataset && !uploading && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-slate-400">
              Upload a file above to get started. Results will appear here once
              you ask a question.
            </div>
          )}
        </div>

        {/* Sidebar — History stub */}
        <aside className="space-y-4">
          <HistoryStub />
        </aside>
      </div>
    </main>
  )
}
