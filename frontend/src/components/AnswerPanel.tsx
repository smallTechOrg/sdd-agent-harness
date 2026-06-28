'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AnswerEvent, StepEvent } from '../lib/types'
import { ChartView } from './ChartView'
import { CodePanel } from './CodePanel'
import { CostLine } from './CostLine'
import { SummaryTable } from './SummaryTable'

interface AnswerPanelProps {
  answer: AnswerEvent
  steps: StepEvent[]
}

export function AnswerPanel({ answer, steps }: AnswerPanelProps) {
  const { answer_text, chart_spec, summary_table, code, usage, daily_total_usd } =
    answer

  return (
    <section
      aria-label="Answer"
      className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      data-testid="answer-panel"
    >
      {/* Plain-language answer — always markdown-rendered. */}
      <div
        className="prose prose-slate max-w-none text-base text-slate-800"
        data-testid="answer-text"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer_text}</ReactMarkdown>
      </div>

      {chart_spec && (
        <div>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Chart
          </h3>
          <ChartView spec={chart_spec} table={summary_table} />
        </div>
      )}

      {summary_table && (
        <div>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Result
          </h3>
          <SummaryTable table={summary_table} />
        </div>
      )}

      {code && <CodePanel code={code} steps={steps} />}

      <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <CostLine usage={usage} dailyTotalUsd={daily_total_usd} />

        {/* Phase 2 stub: follow-up — disabled, clearly labelled. */}
        <div
          className="flex items-center gap-2"
          data-testid="followup-stub"
        >
          <button
            type="button"
            disabled
            aria-disabled="true"
            className="cursor-not-allowed rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-400"
          >
            Ask a follow-up
          </button>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            Conversation memory — Phase 2
          </span>
        </div>
      </div>
    </section>
  )
}
