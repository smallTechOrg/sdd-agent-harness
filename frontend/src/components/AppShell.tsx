'use client'

import { useEffect, useState } from 'react'
import { StubBanner } from '@/components/StubBanner'
import { AnalyseTab } from '@/components/analyse/AnalyseTab'
import { DatabaseTab } from '@/components/database/DatabaseTab'
import { MemoryModal } from '@/components/analyse/MemoryModal'
import { api } from '@/lib/api'

type Tab = 'analyse' | 'database'

/**
 * AppShell — the shell for the Data Analysis Agent.
 *
 * Header (app name + tagline + a labelled "Project notes" stub + the
 * conditional yellow stub-mode banner), a two-tab switcher [Analyse] (default)
 * / [Database], and the responsive panel layout for the active tab.
 *
 * Health is fetched once on mount: its `provider` drives the stub banner (shown
 * only in stub mode) and a subtle "live" indicator when a real provider is set.
 * The Database tab and the Project-notes button remain labelled stubs in Phase 2.
 */
export function AppShell() {
  const [tab, setTab] = useState<Tab>('analyse')
  // undefined = still loading health; string = resolved provider.
  const [provider, setProvider] = useState<string | undefined>(undefined)
  // Global-memory ("Project notes") modal — REAL in Phase 3.
  const [memoryOpen, setMemoryOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then(h => {
        if (!cancelled) setProvider(h.provider)
      })
      .catch(() => {
        // Health failed (e.g. server not reachable yet) — leave provider
        // unresolved so we neither flash a stub banner nor claim "live".
        if (!cancelled) setProvider(undefined)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const isLive = provider === 'gemini' || provider === 'openrouter' || provider === 'anthropic'

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Stub-mode banner — shown only when the backend runs without an LLM key. */}
      <StubBanner provider={provider} />

      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-gray-900">
              Data Analysis Agent
            </h1>
            <p className="text-sm text-gray-500">
              Upload data, ask questions in plain English, get explainable answers.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isLive && (
              <span
                className="inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-2.5 py-1 text-xs font-medium text-green-700"
                title={`Live provider: ${provider}`}
              >
                <span aria-hidden="true" className="h-2 w-2 rounded-full bg-green-500" />
                Live · {provider}
              </span>
            )}
            <button
              type="button"
              onClick={() => setMemoryOpen(true)}
              title="Edit the agent's global project notes (memory)"
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Project notes
            </button>
          </div>
        </div>

        {/* Tab switcher (local UI state — allowed in Phase 1) */}
        <div className="mx-auto max-w-6xl px-4">
          <div role="tablist" aria-label="Views" className="flex gap-1">
            <TabButton
              id="tab-analyse"
              label="Analyse"
              active={tab === 'analyse'}
              onClick={() => setTab('analyse')}
            />
            <TabButton
              id="tab-database"
              label="Database"
              active={tab === 'database'}
              onClick={() => setTab('database')}
            />
          </div>
        </div>
      </header>

      {/* Active tab */}
      <main className="mx-auto max-w-6xl px-4 py-6">
        <div
          role="tabpanel"
          id="panel-analyse"
          aria-labelledby="tab-analyse"
          hidden={tab !== 'analyse'}
        >
          {tab === 'analyse' && (
            <AnalyseTab provider={provider} onOpenMemory={() => setMemoryOpen(true)} />
          )}
        </div>
        <div
          role="tabpanel"
          id="panel-database"
          aria-labelledby="tab-database"
          hidden={tab !== 'database'}
        >
          {tab === 'database' && <DatabaseTab />}
        </div>
      </main>

      {/* Global-memory / Project notes modal (reachable from header + sidebar). */}
      <MemoryModal open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </div>
  )
}

function TabButton({
  id,
  label,
  active,
  onClick,
}: {
  id: string
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      id={id}
      role="tab"
      aria-selected={active}
      aria-controls={`panel-${label.toLowerCase()}`}
      onClick={onClick}
      className={`-mb-px rounded-t-md border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
        active
          ? 'border-blue-600 text-blue-700'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
    >
      {label}
    </button>
  )
}
