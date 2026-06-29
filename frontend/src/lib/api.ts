// API client + types for the Local Data Analyst.
// The frontend is served same-origin under the FastAPI app (basePath '/app'),
// so fetch() uses absolute API paths that hit the FastAPI host directly.
// Responses use the envelope { data, error }; HTTP errors carry { detail: { code, message } }.

export interface SchemaColumn {
  name: string
  type: string
}

/**
 * Per-column profile entry (Phase 2). The backend key for the column label may
 * be `column` OR `name` — read it tolerantly via `profileColumnLabel()`.
 */
export interface ProfileColumn {
  column?: string
  name?: string
  type: string
  null_count: number
  distinct_count: number
  min: number | string | null
  max: number | string | null
  flags: string[]
}

/** Resolve the column label tolerantly (`column` preferred, falls back to `name`). */
export function profileColumnLabel(c: ProfileColumn): string {
  return c.column ?? c.name ?? ''
}

export interface Dataset {
  id: string
  name: string
  row_count: number
  schema: SchemaColumn[]
  profile: ProfileColumn[] | null
}

export type ResultRow = Record<string, unknown>

/** Chart spec (Phase 2) — rendered client-side from the answer `result` rows. */
export interface ChartSpec {
  type: 'bar' | 'line' | 'scatter'
  x: string
  y: string
  series: string | null
  title: string
}

export interface SummaryTableColumn {
  name: string
  type: string
  align: 'left' | 'right'
}

/** Rich summary table (Phase 2). */
export interface SummaryTable {
  columns: SummaryTableColumn[]
  rows: unknown[][]
}

export interface AskResult {
  run_id: string
  dataset_id: string
  status: 'completed' | 'failed'
  question: string
  answer: string | null
  sql: string | null
  result: ResultRow[] | null
  flagged: boolean
  error: string | null
  // Phase 2 — now-real enrichment (any may be null when not applicable).
  chart: ChartSpec | null
  summary_table: SummaryTable | null
  followups: string[] | null
  // Phase 3 placeholder — present as null until then.
  tokens: unknown | null
}

const NETWORK_ERROR = 'Network error — is the server running?'

/** Thrown for any non-2xx response or network failure; message is user-facing. */
export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.detail?.message ?? `Request failed (${res.status})`
  } catch {
    return `Request failed (${res.status})`
  }
}

/** POST /datasets — multipart upload of a CSV file. */
export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  let res: Response
  try {
    res = await fetch('/datasets', { method: 'POST', body: form })
  } catch {
    throw new ApiError(NETWORK_ERROR)
  }
  if (!res.ok) throw new ApiError(await parseError(res))
  const body = await res.json()
  return body.data as Dataset
}

/** POST /datasets/{id}/ask — ask one question; returns the run result (may be a failed run). */
export async function askQuestion(datasetId: string, question: string): Promise<AskResult> {
  let res: Response
  try {
    res = await fetch(`/datasets/${datasetId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  } catch {
    throw new ApiError(NETWORK_ERROR)
  }
  if (!res.ok) throw new ApiError(await parseError(res))
  const body = await res.json()
  return body.data as AskResult
}
