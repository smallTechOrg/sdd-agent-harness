// API client for Pandora. Same-origin calls. The frontend is served under
// basePath `/app`, but the API lives at the ROOT (`/datasets`, `/cost/today`).
// A leading-slash absolute-from-origin path bypasses Next's basePath at fetch
// time (basePath only rewrites <Link>/asset URLs, not raw fetch()), so `/datasets`
// resolves against window.location.origin → http://localhost:8001/datasets.

import type {
  AnswerEvent,
  DatasetResponse,
  ErrorEvent,
  StepEvent,
} from './types'

function apiUrl(path: string): string {
  // Always root-relative against origin, never the /app basePath.
  if (typeof window !== 'undefined') {
    return `${window.location.origin}${path}`
  }
  return path
}

interface ApiErrorBody {
  detail?: { code?: string; message?: string }
}

export async function uploadDataset(file: File): Promise<DatasetResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(apiUrl('/datasets'), { method: 'POST', body: form })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const err = body as ApiErrorBody | null
    throw new Error(
      err?.detail?.message ??
        (res.status === 413
          ? 'That file is over the size limit.'
          : `Couldn't read that file (HTTP ${res.status}).`),
    )
  }
  return (body as { data: DatasetResponse }).data
}

export async function fetchCostToday(): Promise<{
  date: string
  total_usd: number
  question_count: number
} | null> {
  try {
    const res = await fetch(apiUrl('/cost/today'))
    if (!res.ok) return null
    const body = (await res.json()) as {
      data: { date: string; total_usd: number; question_count: number }
    }
    return body.data
  } catch {
    return null
  }
}

export interface AskCallbacks {
  onStep: (step: StepEvent) => void
  onAnswer: (answer: AnswerEvent) => void
  onError: (err: ErrorEvent) => void
}

// Open the SSE stream via POST and parse the text/event-stream body manually
// (EventSource only supports GET; the contract is POST + SSE). We read the
// ReadableStream, split into `event:`/`data:` records separated by a blank line
// (handling both `\n\n` and `\r\n\r\n`), and dispatch each parsed event.
//
// IMPORTANT — this function never silently swallows. If a record fails to parse
// it logs and continues; if the stream ENDS without a terminal `answer`/`error`
// event, it raises a visible error via onError so a regression can never again
// present as "nothing happened" (the button cycled but no panel rendered).

// Split a buffer into complete SSE records (text up to a blank-line separator),
// leaving any trailing partial record in the returned `rest`. Handles CRLF.
function splitSseRecords(buffer: string): { records: string[]; rest: string } {
  const normalised = buffer.replace(/\r\n/g, '\n')
  const parts = normalised.split('\n\n')
  // The last element is a (possibly empty) partial record — keep it buffered.
  const rest = parts.pop() ?? ''
  return { records: parts, rest }
}

// Parse one SSE record into { event, data } per the SSE spec: `event:` names the
// event; one or more `data:` lines are joined with newlines. Lines beginning with
// `:` are comments and ignored.
function parseSseRecord(record: string): { event: string; data: string } | null {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const rawLine of record.split('\n')) {
    const line = rawLine.replace(/\r$/, '')
    if (line === '' || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      eventName = line.slice(6).replace(/^ /, '')
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''))
    }
  }
  if (dataLines.length === 0) return null
  return { event: eventName, data: dataLines.join('\n') }
}

export async function askQuestion(
  datasetId: string,
  question: string,
  cb: AskCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(apiUrl(`/datasets/${datasetId}/ask`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch (e) {
    // Network/transport failure (connection refused, etc.). Surface it.
    cb.onError({
      message:
        e instanceof Error && e.name === 'AbortError'
          ? 'The request was cancelled.'
          : 'Lost the connection to the server. Is it still running?',
      status: 'stuck',
    })
    return
  }

  if (!res.ok || !res.body) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null
    cb.onError({
      message:
        body?.detail?.message ??
        `The question couldn't be processed (HTTP ${res.status}).`,
      status: 'stuck',
    })
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  // Track whether a terminal event arrived; if not, we surface an error below.
  let sawTerminal = false

  const dispatch = (record: string) => {
    const parsed = parseSseRecord(record)
    if (!parsed) return
    let payload: unknown
    try {
      payload = JSON.parse(parsed.data)
    } catch (e) {
      // A malformed frame is a real problem — make it visible, do not swallow.
      console.error('[askQuestion] failed to parse SSE data frame', e, parsed.data)
      return
    }
    if (parsed.event === 'step') {
      cb.onStep(payload as StepEvent)
    } else if (parsed.event === 'answer') {
      sawTerminal = true
      cb.onAnswer(payload as AnswerEvent)
    } else if (parsed.event === 'error') {
      sawTerminal = true
      cb.onError(payload as ErrorEvent)
    }
  }

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { records, rest } = splitSseRecords(buffer)
      buffer = rest
      for (const record of records) {
        if (record.trim()) dispatch(record)
      }
    }
    // Flush any final buffered bytes and any trailing record.
    buffer += decoder.decode()
    if (buffer.trim()) dispatch(buffer)
  } catch (e) {
    // The reader threw mid-stream (e.g. aborted/torn down). Surface it instead
    // of leaving the UI silently stuck.
    if (!sawTerminal) {
      cb.onError({
        message:
          e instanceof Error && e.name === 'AbortError'
            ? 'The request was cancelled.'
            : 'The connection dropped while the answer was streaming.',
        status: 'stuck',
      })
      return
    }
  }

  // The stream closed cleanly but no answer/error ever arrived — never silently
  // no-op; surface a visible stuck state so the panel does not stay empty.
  if (!sawTerminal) {
    cb.onError({
      message:
        'The server finished without returning an answer. Please try again.',
      status: 'stuck',
    })
  }
}
