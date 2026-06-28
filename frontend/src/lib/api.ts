// Typed fetch helpers for the DataChat `/api/...` routes.
// All routes are same-origin relative paths (the static app is served at
// `/app/`, the API lives at `/api/...`, so absolute-from-root paths work).
// See spec/api.md — this file mirrors those response shapes exactly.

// ---------------------------------------------------------------------------
// Response shapes (mirror spec/api.md)
// ---------------------------------------------------------------------------

export interface ProfileColumn {
  name: string
  dtype: string
  missing: number
  distinct?: number
  sample_values?: Array<string | number | boolean | null>
  min?: number | null
  max?: number | null
  mean?: number | null
}

export interface DatasetProfile {
  row_count: number
  columns: ProfileColumn[]
  sample_rows: Array<Record<string, string | number | boolean | null>>
}

export interface UploadResponse {
  dataset_id: string
  name: string
  profile: DatasetProfile
}

// A normalized result table: column headers + row arrays. The backend may send
// this as { columns: [...], rows: [[...], ...] } or a list of record objects.
// `normalizeResultTable` collapses both into this shape for rendering.
export interface ResultTable {
  columns: string[]
  rows: Array<Array<string | number | boolean | null>>
}

export type KeyNumbers = Record<string, string | number | boolean | null>

export interface ThreadMessage {
  id: string
  question: string
  answer: string | null
  status: string
  key_numbers?: KeyNumbers | null
  result_table?: unknown
  cost_usd?: number | null
  created_at: string
}

export interface DatasetDetail {
  dataset_id: string
  name: string
  profile: DatasetProfile
  messages: ThreadMessage[]
}

export interface HistoryItem {
  id: string
  question: string
  status: string
  cost_usd: number | null
  created_at: string
}

export interface MessageDetail {
  id: string
  dataset_id: string
  question: string
  plan: string | null
  generated_code: string | null
  answer: string | null
  key_numbers: KeyNumbers | null
  result_table: unknown
  prompt_tokens: number | null
  completion_tokens: number | null
  cost_usd: number | null
  status: string
  error: string | null
  created_at: string
  completed_at: string | null
}

// ---------------------------------------------------------------------------
// Envelope handling
// ---------------------------------------------------------------------------

interface Envelope<T> {
  data: T
  error: string | null
}

interface ErrorEnvelope {
  detail?: { code?: string; message?: string }
}

/** A typed error carrying the server's real `code` + `message`. */
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

/** Thrown when the server is unreachable / the fetch itself fails. */
export class NetworkError extends Error {
  constructor() {
    super('Network error — is the server running on :8001?')
    this.name = 'NetworkError'
  }
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = `HTTP_${res.status}`
    let message = `Request failed (${res.status})`
    try {
      const body = (await res.json()) as ErrorEnvelope
      if (body.detail?.message) message = body.detail.message
      if (body.detail?.code) code = body.detail.code
    } catch {
      // non-JSON error body — keep the generic message
    }
    throw new ApiError(code, message, res.status)
  }
  const body = (await res.json()) as Envelope<T>
  return body.data
}

async function safeFetch(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch {
    throw new NetworkError()
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** POST /api/datasets — upload a CSV (multipart `file`), get the profile back. */
export async function uploadDataset(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await safeFetch('/api/datasets', { method: 'POST', body: form })
  return parseJson<UploadResponse>(res)
}

/** GET /api/datasets/{id} — reopen a dataset with its profile + thread. */
export async function getDataset(datasetId: string): Promise<DatasetDetail> {
  const res = await safeFetch(`/api/datasets/${datasetId}`)
  return parseJson<DatasetDetail>(res)
}

/** GET /api/datasets/{id}/messages — run-history list. */
export async function getHistory(datasetId: string): Promise<HistoryItem[]> {
  const res = await safeFetch(`/api/datasets/${datasetId}/messages`)
  return parseJson<HistoryItem[]>(res)
}

/** GET /api/messages/{id} — full run detail. */
export async function getMessage(messageId: string): Promise<MessageDetail> {
  const res = await safeFetch(`/api/messages/${messageId}`)
  return parseJson<MessageDetail>(res)
}

// ---------------------------------------------------------------------------
// Normalizers — tolerate either result_table shape from the backend
// ---------------------------------------------------------------------------

/**
 * Normalize a `result_table` into { columns, rows }. The backend may send:
 *   - { columns: string[], rows: any[][] }            (already normalized)
 *   - { columns, data }  (pandas to_dict('split')-ish) → treat `data` as rows
 *   - Array<Record<string, value>>                    (list of record objects)
 *   - { index, columns, data }                        (pandas split orient)
 * Returns null when there is nothing tabular to show.
 */
export function normalizeResultTable(raw: unknown): ResultTable | null {
  if (raw == null) return null

  // Array of record objects
  if (Array.isArray(raw)) {
    if (raw.length === 0) return null
    const records = raw as Array<Record<string, unknown>>
    const columns = Object.keys(records[0])
    const rows = records.map((r) => columns.map((c) => coerceCell(r[c])))
    return { columns, rows }
  }

  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    const columns = Array.isArray(obj.columns) ? (obj.columns as unknown[]).map(String) : null
    const rowsSource =
      (Array.isArray(obj.rows) && obj.rows) ||
      (Array.isArray(obj.data) && obj.data) ||
      null

    if (columns && rowsSource) {
      const rows = (rowsSource as unknown[]).map((row) =>
        Array.isArray(row)
          ? (row as unknown[]).map(coerceCell)
          : columns.map((c) => coerceCell((row as Record<string, unknown>)[c])),
      )
      return { columns, rows }
    }

    // Fallback: a flat record { key: value } → render as a 2-col table
    const entries = Object.entries(obj)
    if (entries.length > 0) {
      return {
        columns: ['key', 'value'],
        rows: entries.map(([k, v]) => [k, coerceCell(v)]),
      }
    }
  }

  return null
}

function coerceCell(v: unknown): string | number | boolean | null {
  if (v == null) return null
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'string') return v
  return String(v)
}

/** Format a USD cost compactly (e.g. $0.0007). */
export function formatCost(cost: number | null | undefined): string {
  if (cost == null) return '—'
  if (cost === 0) return '$0.00'
  if (cost < 0.01) return `$${cost.toFixed(4)}`
  return `$${cost.toFixed(2)}`
}
