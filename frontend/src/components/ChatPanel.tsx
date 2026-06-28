'use client'
import { useState, useRef, useEffect, useCallback } from 'react'
import { ChatMessage, ExecutionStep } from '@/types'
import PlotlyChart from '@/components/PlotlyChart'
import CodeAccordion from '@/components/CodeAccordion'
import CostFooter from '@/components/CostFooter'
import StubPanel from '@/components/StubPanel'

interface Props { selectedFileId: string | null }

export default function ChatPanel({ selectedFileId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    const question = input.trim()
    if (!question || !selectedFileId || isStreaming) return

    setInput('')
    const userMsgId = crypto.randomUUID()
    const assistantMsgId = crypto.randomUUID()

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', text: question },
      { id: assistantMsgId, role: 'assistant', text: '', isStreaming: true, steps: [] },
    ])
    setIsStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await fetch('/api/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ question, file_ids: [selectedFileId], session_id: null }),
        signal: ctrl.signal,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: { message: 'Request failed' } }))
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, isStreaming: false, error: err.detail?.message || 'Request failed' }
              : m
          )
        )
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const updateMsg = (updater: (m: ChatMessage) => ChatMessage) => {
        setMessages((prev) => prev.map((m) => (m.id === assistantMsgId ? updater(m) : m)))
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          let ev: Record<string, unknown>
          try { ev = JSON.parse(line.slice(6)) } catch { continue }

          switch (ev.type) {
            case 'token':
              updateMsg((m) => ({ ...m, text: (ev.text as string) || '' }))
              break
            case 'code_step':
              updateMsg((m) => ({
                ...m,
                steps: [
                  ...(m.steps ?? []),
                  {
                    iteration: ev.iteration as number,
                    code: ev.code as string,
                    stdout: ev.stdout as string,
                    stderr: ev.stderr as string,
                    success: ev.success as boolean,
                  } satisfies ExecutionStep,
                ],
              }))
              break
            case 'chart':
              updateMsg((m) => ({ ...m, chart: ev.plotly as ChatMessage['chart'] }))
              break
            case 'cost':
              updateMsg((m) => ({
                ...m,
                costInfo: {
                  input_tokens: ev.input_tokens as number,
                  output_tokens: ev.output_tokens as number,
                  cost_usd: ev.cost_usd as number,
                },
              }))
              break
            case 'error':
              updateMsg((m) => ({ ...m, error: ev.message as string }))
              break
            case 'clarification':
              updateMsg((m) => ({ ...m, clarification: ev.question as string }))
              break
            case 'done':
              updateMsg((m) => ({ ...m, isStreaming: false }))
              break
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, isStreaming: false, error: 'Connection failed' }
            : m
        )
      )
    } finally {
      setIsStreaming(false)
    }
  }, [input, selectedFileId, isStreaming])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Session history stub */}
      <div className="px-4 pt-3">
        <StubPanel label="Session history" sublabel="Coming in Phase 2" />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-16">
            <p className="text-lg font-medium">Data Analysis Agent</p>
            <p className="text-sm mt-2">Upload a CSV file and ask a question about your data.</p>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
            data-testid={`message-${msg.role}`}
          >
            <div className={`max-w-2xl rounded-lg px-4 py-3 ${msg.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-white border border-gray-200 text-gray-900'}`}>
              {msg.role === 'user' ? (
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
              ) : (
                <>
                  {msg.isStreaming && !msg.text && !msg.error && (
                    <p className="text-sm text-gray-400 animate-pulse">Analysing…</p>
                  )}
                  {msg.error && (
                    <p className="text-sm text-red-600" role="alert">Error: {msg.error}</p>
                  )}
                  {msg.clarification && (
                    <p className="text-sm text-amber-700">Clarification needed: {msg.clarification}</p>
                  )}
                  {msg.text && (
                    <p className="text-sm whitespace-pre-wrap" data-testid="answer-text">{msg.text}</p>
                  )}
                  {msg.chart && <PlotlyChart plotlySpec={msg.chart} />}
                  {msg.steps && msg.steps.length > 0 && <CodeAccordion steps={msg.steps} />}
                  {msg.costInfo && (
                    <CostFooter
                      inputTokens={msg.costInfo.input_tokens}
                      outputTokens={msg.costInfo.output_tokens}
                      costUsd={msg.costInfo.cost_usd}
                    />
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4 pt-2 border-t border-gray-200">
        {!selectedFileId && (
          <p className="text-xs text-amber-600 mb-2">Upload a CSV file first to start asking questions.</p>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!selectedFileId || isStreaming}
            placeholder={selectedFileId ? 'Ask a question about your data…' : 'Upload a file first'}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 disabled:bg-gray-50"
            rows={2}
            data-testid="question-input"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !selectedFileId || isStreaming}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors self-end"
            data-testid="send-btn"
          >
            {isStreaming ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
