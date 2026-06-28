// SSE client for `POST /api/datasets/{id}/ask`.
//
// The endpoint returns `text/event-stream` in response to a POST. The native
// `EventSource` API only supports GET, so we use `fetch()` + a ReadableStream
// reader and parse the `event:` / `data:` lines ourselves, buffering partial
// lines across chunk boundaries.
//
// See spec/api.md for the event sequence:
//   status → plan → code → token(*) → done | error
//
// `streamAnalysis` resolves when the stream ends (after `done` or `error`) and
// rejects only on a transport-level failure (server unreachable, non-2xx
// pre-stream response). The `error` SSE event is delivered via `onError` — it
// rides the stream and is NOT a thrown rejection.

import { ApiError, NetworkError, type KeyNumbers } from './api'

export interface StatusEvent {
  step: 'planning' | 'generating_code' | 'executing' | 'synthesizing' | string
}

export interface PlanEvent {
  plan: string
}

export interface CodeEvent {
  code: string
}

export interface TokenEvent {
  text: string
}

export interface DoneEvent {
  message_id: string
  key_numbers?: KeyNumbers | null
  result_table?: unknown
  prompt_tokens?: number | null
  completion_tokens?: number | null
  cost_usd?: number | null
  status: string
}

export interface StreamErrorEvent {
  message_id?: string
  error: string
  code?: string
  status: string
}

export interface StreamCallbacks {
  onStatus?: (e: StatusEvent) => void
  onPlan?: (e: PlanEvent) => void
  onCode?: (e: CodeEvent) => void
  onToken?: (e: TokenEvent) => void
  onDone?: (e: DoneEvent) => void
  onError?: (e: StreamErrorEvent) => void
}

interface RawEvent {
  event: string
  data: string
}

/**
 * Open the analysis SSE stream and dispatch events to the callbacks.
 * @param signal optional AbortSignal to cancel the stream.
 * @returns a promise that resolves when the stream completes.
 * @throws ApiError on a pre-stream 4xx (e.g. EMPTY_QUESTION, NOT_FOUND),
 *         NetworkError if the server is unreachable.
 */
export async function streamAnalysis(
  datasetId: string,
  question: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`/api/datasets/${datasetId}/ask`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    throw new NetworkError()
  }

  // A pre-stream failure arrives as a normal JSON error envelope, not SSE.
  if (!res.ok) {
    let code = `HTTP_${res.status}`
    let message = `Request failed (${res.status})`
    try {
      const body = (await res.json()) as { detail?: { code?: string; message?: string } }
      if (body.detail?.message) message = body.detail.message
      if (body.detail?.code) code = body.detail.code
    } catch {
      // keep generic message
    }
    throw new ApiError(code, message, res.status)
  }

  if (!res.body) {
    throw new NetworkError()
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Events are separated by a blank line. Normalize CRLF first.
      let sepIndex: number
      buffer = buffer.replace(/\r\n/g, '\n')
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawBlock = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)
        const parsed = parseEventBlock(rawBlock)
        if (parsed) dispatch(parsed, callbacks)
      }
    }
    // Flush any trailing event without a final blank line.
    const tail = buffer.trim()
    if (tail) {
      const parsed = parseEventBlock(tail)
      if (parsed) dispatch(parsed, callbacks)
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    throw new NetworkError()
  } finally {
    reader.releaseLock()
  }
}

function parseEventBlock(block: string): RawEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue // SSE comment / keepalive
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      // Per spec a leading single space after the colon is stripped.
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

function dispatch(raw: RawEvent, cb: StreamCallbacks): void {
  let payload: unknown
  try {
    payload = JSON.parse(raw.data)
  } catch {
    return // ignore unparseable data lines
  }
  switch (raw.event) {
    case 'status':
      cb.onStatus?.(payload as StatusEvent)
      break
    case 'plan':
      cb.onPlan?.(payload as PlanEvent)
      break
    case 'code':
      cb.onCode?.(payload as CodeEvent)
      break
    case 'token':
      cb.onToken?.(payload as TokenEvent)
      break
    case 'done':
      cb.onDone?.(payload as DoneEvent)
      break
    case 'error':
      cb.onError?.(payload as StreamErrorEvent)
      break
    default:
      // unknown event — ignore
      break
  }
}

/** Human-readable label for a status step. */
export function stepLabel(step: string): string {
  switch (step) {
    case 'planning':
      return 'Planning…'
    case 'generating_code':
      return 'Generating code…'
    case 'executing':
      return 'Running locally…'
    case 'synthesizing':
      return 'Writing answer…'
    default:
      return step
  }
}

export const STEP_ORDER = ['planning', 'generating_code', 'executing', 'synthesizing'] as const
