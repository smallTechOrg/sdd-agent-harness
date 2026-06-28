'use client'

import {
  normalizeResultTable,
  formatCost,
  type KeyNumbers as KeyNumbersData,
} from '@/lib/api'
import KeyNumbers from './KeyNumbers'
import ResultTable from './ResultTable'
import CodePanel from './CodePanel'
import StepIndicator from './StepIndicator'
import { stepLabel } from '@/lib/sse'
import { StubCard } from './Stub'

export interface TurnData {
  /** stable key for React */
  id: string
  question: string
  answer: string
  code: string
  plan: string
  keyNumbers: KeyNumbersData | null
  resultTable: unknown
  promptTokens: number | null
  completionTokens: number | null
  costUsd: number | null
  status: 'streaming' | 'completed' | 'failed'
  /** live step while streaming */
  step: string | null
  /** real error message + offending code on failure */
  error: string | null
  errorCode: string | null
}

/**
 * Renders one chat turn: the question, then the streamed/streamed answer with
 * its key numbers, summary table, collapsible code, tokens+cost, and the
 * labelled follow-up + charts stubs. On failure, an error card with the real
 * error + offending code.
 */
export default function AnswerTurn({ turn }: { turn: TurnData }) {
  const table = normalizeResultTable(turn.resultTable)
  const streaming = turn.status === 'streaming'
  const failed = turn.status === 'failed'

  return (
    <div className="space-y-3">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-3.5 py-2 text-sm text-white">
          {turn.question}
        </div>
      </div>

      {/* Answer block */}
      <div className="rounded-2xl rounded-bl-sm border border-gray-200 bg-white px-4 py-3 shadow-sm">
        {/* Streaming step indicator */}
        {streaming && turn.step && (
          <div className="mb-3">
            <StepIndicator current={turn.step} />
          </div>
        )}

        {failed ? (
          <ErrorCard error={turn.error} code={turn.errorCode ?? turn.code} />
        ) : (
          <>
            {/* Streamed answer text */}
            {turn.answer ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
                {turn.answer}
                {streaming && <span className="ml-0.5 animate-pulse text-gray-400">▍</span>}
              </p>
            ) : streaming ? (
              <p className="text-sm text-gray-400">
                {turn.step ? stepLabel(turn.step) : 'Working…'}
              </p>
            ) : null}

            {/* Key numbers strip */}
            {turn.keyNumbers && Object.keys(turn.keyNumbers).length > 0 && (
              <div className="mt-3">
                <KeyNumbers numbers={turn.keyNumbers} />
              </div>
            )}

            {/* Summary table */}
            {table && (
              <div className="mt-3">
                <ResultTable table={table} />
              </div>
            )}

            {/* Charts stub (Phase 2) */}
            {(table || turn.keyNumbers) && !streaming && (
              <div className="mt-3">
                <StubCard title="Charts" phase="P2">
                  Interactive charts for this answer will render here.
                </StubCard>
              </div>
            )}

            {/* Collapsible code */}
            {turn.code && (
              <div className="mt-3">
                <CodePanel code={turn.code} />
              </div>
            )}

            {/* Tokens + cost */}
            {!streaming && (turn.promptTokens != null || turn.costUsd != null) && (
              <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-gray-400">
                {turn.promptTokens != null && (
                  <span>{turn.promptTokens.toLocaleString()} prompt tokens</span>
                )}
                {turn.completionTokens != null && (
                  <span>{turn.completionTokens.toLocaleString()} completion tokens</span>
                )}
                <span>· {formatCost(turn.costUsd)}</span>
              </div>
            )}

            {/* AI follow-up suggestions stub (Phase 2) */}
            {!streaming && (table || turn.answer) && (
              <div className="mt-3">
                <StubCard title="AI follow-up suggestions" phase="P2">
                  Suggested next questions will appear here.
                </StubCard>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ErrorCard({ error, code }: { error: string | null; code: string | null }) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-700">
        Analysis failed
      </div>
      <pre className="mb-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-red-800">
        {error || 'The run failed without a message.'}
      </pre>
      {code && (
        <>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-red-600">
            Offending code
          </div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-red-900/90 px-2.5 py-2 text-xs text-red-50">
            <code>{code}</code>
          </pre>
        </>
      )}
    </div>
  )
}
