// Same-origin API client. The static UI is served at /app but the API lives at
// the site root, so we call absolute-from-origin relative paths (e.g. "/datasets").

export interface ColumnSchema {
  name: string
  type: string
}

export interface Dataset {
  id: string
  name: string
  session_id?: string
  row_count: number
  schema: ColumnSchema[]
  sample_rows?: Array<Array<string | number | null>>
  created_at?: string
}

export interface AskResult {
  run_id: string
  narrative: string
  sql: string
  columns: string[]
  rows: Array<Array<string | number | null>>
  row_count: number
  duration_ms: number
  status: string
}

export interface AuditEntry {
  id: string
  dataset_id: string
  nl_question: string
  generated_sql: string
  row_count: number | null
  duration_ms: number | null
  status: string
  error_message: string | null
  created_at: string
}

interface ErrorEnvelope {
  detail?: { code?: string; message?: string } | string
  error?: { message?: string } | null
  message?: string
}

/**
 * Thrown on any non-2xx response. Carries the HTTP status so callers can map
 * specific codes (400 / 502) to tailored copy.
 */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function extractMessage(body: ErrorEnvelope | null, status: number): string {
  if (body) {
    if (typeof body.detail === 'object' && body.detail?.message) return body.detail.message
    if (typeof body.detail === 'string' && body.detail) return body.detail
    if (body.error?.message) return body.error.message
    if (body.message) return body.message
  }
  return `Request failed (${status})`
}

async function unwrap<T>(res: Response): Promise<T> {
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  if (!res.ok) {
    throw new ApiError(extractMessage(body as ErrorEnvelope, res.status), res.status)
  }
  const envelope = body as { data?: T } | null
  return (envelope?.data ?? (body as T)) as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError('Network error — is the server running?', 0)
  }
  return unwrap<T>(res)
}

export function listDatasets(): Promise<Dataset[]> {
  return request<Dataset[]>('/datasets')
}

export function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  return request<Dataset>('/datasets', { method: 'POST', body: form })
}

export function ask(datasetId: string, question: string): Promise<AskResult> {
  return request<AskResult>('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, question }),
  })
}

export function listAudit(): Promise<AuditEntry[]> {
  return request<AuditEntry[]>('/audit')
}

export const AUDIT_EXPORT_URL = '/audit/export?format=csv'
