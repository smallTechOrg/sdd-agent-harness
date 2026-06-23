'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  listAudit,
  listDatasets,
  type AskResult,
  type AuditEntry,
  type Dataset,
} from './lib/api'
import UploadPanel from './components/UploadPanel'
import DatasetList from './components/DatasetList'
import AskBox from './components/AskBox'
import ResultView from './components/ResultView'
import AuditLog from './components/AuditLog'
import StubCard from './components/StubCard'

const STUBS = [
  {
    title: 'Charts',
    description: 'Auto-generated visualizations of your query results.',
  },
  {
    title: 'Dashboards',
    description: 'Pin multiple results into a saved, shareable dashboard.',
  },
  {
    title: 'Cross-Dataset Query',
    description: 'Ask one question that joins across several datasets.',
  },
]

export default function Home() {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetsLoading, setDatasetsLoading] = useState(true)
  const [selected, setSelected] = useState<Dataset | null>(null)

  const [result, setResult] = useState<AskResult | null>(null)

  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [auditLoading, setAuditLoading] = useState(true)

  const refreshDatasets = useCallback(async () => {
    setDatasetsLoading(true)
    try {
      const data = await listDatasets()
      setDatasets(data)
      setSelected(prev => {
        if (prev) {
          const still = data.find(d => d.id === prev.id)
          if (still) return still
        }
        return data[0] ?? null
      })
    } catch {
      setDatasets([])
    } finally {
      setDatasetsLoading(false)
    }
  }, [])

  const refreshAudit = useCallback(async () => {
    setAuditLoading(true)
    try {
      setAudit(await listAudit())
    } catch {
      setAudit([])
    } finally {
      setAuditLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshDatasets()
    refreshAudit()
  }, [refreshDatasets, refreshAudit])

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">Data Analyst</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload your data, ask in plain English, get an analyst&rsquo;s answer — your rows stay
          on your machine.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Datasets */}
        <section className="space-y-4 lg:col-span-1" aria-labelledby="datasets-heading">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 id="datasets-heading" className="mb-3 text-lg font-semibold text-gray-900">
              Datasets
            </h2>
            <UploadPanel onUploaded={refreshDatasets} />
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <DatasetList
              datasets={datasets}
              loading={datasetsLoading}
              selectedId={selected?.id ?? null}
              onSelect={setSelected}
            />
          </div>
        </section>

        {/* Center: Ask + Result */}
        <section className="space-y-4 lg:col-span-2" aria-labelledby="ask-heading">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <h2 id="ask-heading" className="mb-3 text-lg font-semibold text-gray-900">
              Ask a question
            </h2>
            <AskBox dataset={selected} onResult={setResult} onCompleted={refreshAudit} />
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <ResultView result={result} />
          </div>
        </section>
      </div>

      {/* Audit Log */}
      <section className="mt-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <AuditLog entries={audit} loading={auditLoading} />
      </section>

      {/* Coming soon stubs */}
      <section className="mt-8" aria-labelledby="coming-soon-heading">
        <h2 id="coming-soon-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
          Coming soon
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {STUBS.map(stub => (
            <StubCard key={stub.title} title={stub.title} description={stub.description} />
          ))}
        </div>
      </section>
    </main>
  )
}
