// Thin client for the Local Data Analyst API.
// All calls are same-origin and relative (the page is served under /app/, the
// API routes live at the root). NEVER hardcode the host or the /app prefix.

// ---- Types mirroring spec/api.md ----

export interface ProfileColumn {
  name: string
  type: string
  nulls?: number
  distinct?: number
  min?: number | string | null
  max?: number | string | null
}

export interface DatasetProfile {
  row_count: number
  columns: ProfileColumn[]
}

export interface DatasetColumn {
  name: string
  type: string
}

export interface Dataset {
  id: string
  name: string
  row_count: number
  columns: DatasetColumn[]
  profile: DatasetProfile
  status: string
}

export interface KeyNumber {
  label: string
  value: string | number
}

export interface ChartPayload {
  type: 'bar' | 'line' | 'pie' | 'table'
  x?: string
  y?: string
  data?: Array<Record<string, unknown>>
}

export interface SummaryTable {
  columns: string[]
  rows: Array<Array<unknown>>
}

export interface TraceStep {
  step: string
  ok: boolean
  latency_ms?: number
  error?: string
  sql?: string
}

export interface AskResult {
  run_id: string
  status: 'completed' | 'failed'
  answer: string | null
  key_numbers: KeyNumber[] | null
  chart: ChartPayload | null
  table: SummaryTable | null
  plan: string | null
  sql: string | null
  trace: TraceStep[]
  cost_usd: number | null
  error_message?: string | null
}

// Lightweight summary returned by GET /datasets (the sidebar list). NOT the full
// profile — the page fetches the full Dataset via getDataset(id) on selection.
export interface DatasetSummary {
  id: string
  name: string
  row_count: number
  status: string
  question_count: number
  created_at: string
}

// A persisted question run, as returned by GET /datasets/{id}/runs. It is the
// live AskResult superset PLUS the two history-only fields, so the existing
// AnswerPanel renders a re-opened run with no new component.
export type RunRecord = AskResult & {
  question: string
  created_at: string
}

// Thrown when the API returns an HTTP error envelope ({detail:{code,message}}).
export class ApiError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

// Thrown when the request never reached the server (server down, CORS, etc.).
export class NetworkError extends Error {
  constructor() {
    super('Network error — is the server running?')
    this.name = 'NetworkError'
  }
}

async function parseEnvelope<T>(res: Response): Promise<T> {
  let body: unknown
  try {
    body = await res.json()
  } catch {
    if (!res.ok) {
      throw new ApiError('UNKNOWN', `Request failed (${res.status})`, res.status)
    }
    throw new ApiError('UNKNOWN', 'Malformed response from server', res.status)
  }
  const b = body as { data?: T; error?: unknown; detail?: { code?: string; message?: string } }
  if (!res.ok) {
    const code = b.detail?.code ?? 'UNKNOWN'
    const message = b.detail?.message ?? `Request failed (${res.status})`
    throw new ApiError(code, message, res.status)
  }
  return b.data as T
}

export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  let res: Response
  try {
    res = await fetch('/datasets', { method: 'POST', body: form })
  } catch {
    throw new NetworkError()
  }
  return parseEnvelope<Dataset>(res)
}

export async function getDataset(id: string): Promise<Dataset> {
  let res: Response
  try {
    res = await fetch(`/datasets/${encodeURIComponent(id)}`)
  } catch {
    throw new NetworkError()
  }
  return parseEnvelope<Dataset>(res)
}

export async function askQuestion(datasetId: string, question: string): Promise<AskResult> {
  let res: Response
  try {
    res = await fetch(`/datasets/${encodeURIComponent(datasetId)}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  } catch {
    throw new NetworkError()
  }
  // Agent failures arrive as HTTP 200 with status:"failed" in the body, so they
  // flow through parseEnvelope normally (not as ApiError). Only transport-level
  // HTTP errors (404/422) raise ApiError.
  return parseEnvelope<AskResult>(res)
}

// List every dataset for the sidebar, newest first. Pure DB read, no LLM call —
// an empty list is a valid state (the API returns []).
export async function getDatasets(): Promise<DatasetSummary[]> {
  let res: Response
  try {
    res = await fetch('/datasets')
  } catch {
    throw new NetworkError()
  }
  return parseEnvelope<DatasetSummary[]>(res)
}

// The question/run history for one dataset, newest first. Pure DB read, no LLM
// call — re-opening a past run is instant. Each record is the AskResult shape
// plus question + created_at, so AnswerPanel renders it unchanged.
export async function getDatasetRuns(id: string): Promise<RunRecord[]> {
  let res: Response
  try {
    res = await fetch(`/datasets/${encodeURIComponent(id)}/runs`)
  } catch {
    throw new NetworkError()
  }
  return parseEnvelope<RunRecord[]>(res)
}
