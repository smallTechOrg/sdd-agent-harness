'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  ApiError,
  NetworkError,
  askQuestion,
  getDataset,
  getDatasetRuns,
  getDatasets,
  uploadDataset,
  type AskResult,
  type Dataset,
  type DatasetSummary,
  type RunRecord,
} from '../lib/api'
import { AnswerPanel } from '../components/AnswerPanel'
import { AskBox } from '../components/AskBox'
import { ProfileCard } from '../components/ProfileCard'
import { RunHistory } from '../components/RunHistory'
import { Sidebar } from '../components/Sidebar'
import { Uploader } from '../components/Uploader'

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [result, setResult] = useState<AskResult | null>(null)
  const [askLoading, setAskLoading] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)
  // True when `result` is a re-opened persisted run (from history), so the UI
  // can mark it "from history" — no LLM call was made to produce it.
  const [fromHistory, setFromHistory] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  // ---- Sidebar dataset list (GET /datasets) ----
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  // ---- Run history for the selected dataset (GET /datasets/{id}/runs) ----
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)

  // Load the dataset list. Pure DB read — proves persistence across sessions: a
  // returning user sees their past datasets without re-uploading.
  const refreshDatasets = useCallback(async (): Promise<DatasetSummary[]> => {
    setListLoading(true)
    setListError(null)
    try {
      const list = await getDatasets()
      setDatasets(list)
      return list
    } catch (e) {
      if (e instanceof NetworkError) {
        setListError('Couldn’t load your datasets — is the server running?')
      } else if (e instanceof ApiError) {
        setListError(e.message || 'Couldn’t load your datasets.')
      } else {
        setListError('Couldn’t load your datasets.')
      }
      return []
    } finally {
      setListLoading(false)
    }
  }, [])

  // On mount, populate the sidebar from the persisted list.
  useEffect(() => {
    void refreshDatasets()
  }, [refreshDatasets])

  // Load the run history for a dataset. Pure DB read — instant, no LLM.
  const loadRuns = useCallback(async (datasetId: string) => {
    setRunsLoading(true)
    setRunsError(null)
    try {
      const history = await getDatasetRuns(datasetId)
      setRuns(history)
    } catch (e) {
      setRuns([])
      if (e instanceof NetworkError) {
        setRunsError('Couldn’t load run history — is the server running?')
      } else if (e instanceof ApiError) {
        setRunsError(e.message || 'Couldn’t load run history.')
      } else {
        setRunsError('Couldn’t load run history.')
      }
    } finally {
      setRunsLoading(false)
    }
  }, [])

  // Select a dataset from the sidebar: re-load its full profile (so the Ask box
  // targets it) and its run history. No LLM call on either fetch.
  async function handleSelectDataset(id: string) {
    if (id === dataset?.id) return
    // Clear any answer being shown for the previous dataset.
    setResult(null)
    setAskError(null)
    setFromHistory(false)
    setActiveRunId(null)
    try {
      const ds = await getDataset(id)
      setDataset(ds)
    } catch (e) {
      if (e instanceof NetworkError) {
        setUploadError('Network error — is the server running?')
      } else if (e instanceof ApiError) {
        setUploadError(e.message || 'Couldn’t load that dataset.')
      } else {
        setUploadError('Couldn’t load that dataset.')
      }
      return
    }
    setUploadError(null)
    await loadRuns(id)
  }

  // Re-open a persisted run: render it via the existing AnswerPanel from the
  // stored RunRecord. NO askQuestion call, no LLM, no ask spinner — instant.
  function handleReopenRun(run: RunRecord) {
    setAskError(null)
    setResult(run)
    setFromHistory(true)
    setActiveRunId(run.run_id)
  }

  async function handleUpload(file: File) {
    setUploadLoading(true)
    setUploadError(null)
    setResult(null)
    setAskError(null)
    setFromHistory(false)
    setActiveRunId(null)
    try {
      const ds = await uploadDataset(file)
      setDataset(ds)
      // Refresh the sidebar list and load this new dataset's (empty) history.
      await refreshDatasets()
      await loadRuns(ds.id)
    } catch (e) {
      if (e instanceof NetworkError) {
        setUploadError('Network error — is the server running?')
      } else if (e instanceof ApiError) {
        setUploadError(e.message || "Couldn’t read that CSV — check it’s a valid file")
      } else {
        setUploadError("Couldn’t read that CSV — check it’s a valid file")
      }
    } finally {
      setUploadLoading(false)
    }
  }

  async function handleAsk(question: string) {
    if (!dataset) return
    setAskLoading(true)
    setAskError(null)
    setResult(null)
    setFromHistory(false)
    setActiveRunId(null)
    try {
      const res = await askQuestion(dataset.id, question)
      setResult(res) // status may be "completed" or "failed"; AnswerPanel handles both
      setActiveRunId(res.run_id)
      // A new question appends to the top of this dataset's history; refresh both
      // the history list and the sidebar (question_count changed).
      await loadRuns(dataset.id)
      await refreshDatasets()
    } catch (e) {
      if (e instanceof NetworkError) {
        setAskError('Network error — is the server running?')
      } else if (e instanceof ApiError) {
        setAskError(e.message || `Request failed (${e.status})`)
      } else {
        setAskError('Something went wrong running that question.')
      }
    } finally {
      setAskLoading(false)
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Local Data Analyst</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload a CSV, ask a question, get an auditable answer — all on your machine.
        </p>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row">
        <Sidebar
          datasets={datasets}
          activeId={dataset?.id ?? null}
          listLoading={listLoading}
          listError={listError}
          onSelect={handleSelectDataset}
        />

        <div className="min-w-0 flex-1 space-y-6">
          <Uploader
            onUpload={handleUpload}
            loading={uploadLoading}
            error={uploadError}
            hasDataset={!!dataset}
          />

          {dataset && <ProfileCard dataset={dataset} />}

          {dataset && <AskBox onAsk={handleAsk} loading={askLoading} />}

          {/* Transport-level ask error (network / 404 / 422) — distinct from an
              agent "failed" result, which renders inside AnswerPanel. */}
          {askError && (
            <div
              data-testid="ask-error"
              role="alert"
              className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm font-medium text-red-700"
            >
              {askError}
            </div>
          )}

          {result && (
            <div data-testid={fromHistory ? 'reopened-run' : 'fresh-run'}>
              {fromHistory && (
                <div
                  data-testid="from-history-label"
                  className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-500"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
                  from history — re-opened, no new question asked
                </div>
              )}
              <AnswerPanel result={result} />
            </div>
          )}

          {/* Run history for the selected dataset (REAL in Phase 2). */}
          {dataset && (
            <RunHistory
              runs={runs}
              loading={runsLoading}
              error={runsError}
              activeRunId={activeRunId}
              onReopen={handleReopenRun}
            />
          )}

          {!dataset && !uploadLoading && (
            <div
              data-testid="empty-state"
              className="rounded-xl border border-dashed border-gray-200 bg-white/60 p-10 text-center"
            >
              <p className="text-sm text-gray-400">
                Upload a CSV above to see its profile and start asking questions.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  )
}
