/**
 * API helper for the Data Analysis Agent frontend.
 *
 * The backend (FastAPI) is served single-origin: the UI lives under `/app/`,
 * the API at the origin root. All fetches here use ROOT-RELATIVE paths
 * (e.g. "/health", "/upload") which resolve to the origin root regardless of
 * the `/app` basePath — so the same build works in dev and in the bundled
 * single-origin server.
 *
 * Envelope contract (spec/api.md):
 *   success: { "data": <payload>, "error": null }   (HTTP 2xx)
 *   error:   { "detail": { "code": <str>, "message": <str> } }   (HTTP 4xx/5xx)
 *
 * `unwrap()` returns the success payload and throws an `ApiError` carrying the
 * `code` + `message` on the error shape, so callers can branch on
 * `err.code === "duplicate_dataset"` etc.
 */

/** Error thrown for any non-2xx response, carrying the contract's code/message. */
export class ApiError extends Error {
  code: string
  status: number
  /** The raw `detail` object (may carry extra fields like `existing_*`). */
  detail: Record<string, unknown> | null

  constructor(
    code: string,
    message: string,
    status: number,
    detail: Record<string, unknown> | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.detail = detail
  }
}

/** Parse a fetch Response per the envelope contract; throw ApiError on failure. */
async function unwrap<T>(res: Response): Promise<T> {
  let body: unknown = null
  const text = await res.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      // Non-JSON body (e.g. a proxy error page) — fall through to a generic error.
      body = null
    }
  }

  if (!res.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? (body as { detail: unknown }).detail
        : null

    if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      const code = typeof d.code === 'string' ? d.code : 'error'
      const message =
        typeof d.message === 'string' ? d.message : `Request failed (${res.status})`
      throw new ApiError(code, message, res.status, d)
    }

    // Fallback when the error body isn't in the documented shape.
    const message =
      typeof detail === 'string' ? detail : `Request failed (${res.status})`
    throw new ApiError('error', message, res.status, null)
  }

  // Success: unwrap { data, error } when present, else return the raw body.
  if (body && typeof body === 'object' && 'data' in body) {
    return (body as { data: T }).data
  }
  return body as T
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: 'GET', headers: { Accept: 'application/json' } })
  return unwrap<T>(res)
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return unwrap<T>(res)
}

async function patchJson<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  return unwrap<T>(res)
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: 'DELETE', headers: { Accept: 'application/json' } })
  return unwrap<T>(res)
}

// ---------------------------------------------------------------------------
// Response types (subset of spec/api.md needed in Phase 2)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string
  provider: string
}

export interface UploadResponse {
  dataset_id: string
  filename: string
  format: string
  row_count: number
  col_count: number
  columns: string[]
  context: string | null
  auto_notes_status: string | null
}

export interface DatasetSummary {
  id: string
  filename: string
  row_count: number
  col_count: number
  format: string
  origin: string
  stale?: boolean
  [key: string]: unknown
}

export interface ColumnSchema {
  name: string
  dtype: string
}

export interface DatasetDetail extends DatasetSummary {
  columns_schema: ColumnSchema[]
  context: string | null
  derivation_code: string | null
  auto_notes_status: string | null
}

export interface PreviewResponse {
  columns: string[]
  rows: unknown[][]
}

export interface AskStep {
  action: string
  result: string
  is_error: boolean
}

/**
 * Response from POST /ask. Two variants share this shape (spec/api.md):
 *  - `type: "answer"`       — the full analysis result (answer + steps + tokens…)
 *  - `type: "clarification"`— a thin pre-flight (C26) result carrying
 *    `clarification_question`, `run_id`, and `session_id` only; the answer/steps
 *    fields are absent, so they are typed optional here.
 */
export interface AskResponse {
  type: string
  run_id: string
  session_id?: string | null
  dataset_ids?: string[]
  derived_dataset_ids?: string[]
  datasets_used?: string[]
  selector_reasoning?: string | null
  answer_markdown?: string
  answer_html?: string
  iteration_count?: number
  tokens_input?: number
  tokens_output?: number
  status?: string
  is_best_effort?: boolean
  steps?: AskStep[]
  suggested_questions?: string[]
  prompt_breakdown?: Record<string, unknown>
  // Clarification variant (type === "clarification"):
  clarification_question?: string
}

/** Arguments for the `ask` wrapper — datasets are optional (selector picks). */
export interface AskArgs {
  question: string
  /** Explicit multi-dataset selection (C19 selector runs when omitted/empty). */
  datasetIds?: string[]
  /** Single-dataset convenience (back-compat with the Phase-2 caller). */
  datasetId?: string
  /** Continue an existing session; omit to start a new one server-side. */
  sessionId?: string | null
  /** Skip the C26 clarification pre-flight (used on clarification re-submit). */
  skipClarification?: boolean
}

export interface CurrentRun {
  run_id: string | null
  status: string
  iteration_count: number
  max_iterations: number
}

/** GET /stats/daily — today's aggregated usage (spec/api.md). */
export interface DailyStats {
  date: string
  model: string
  tokens_input: number
  tokens_output: number
  query_count: number
  context_limit: number
}

// ---------------------------------------------------------------------------
// Session types (Phase 3)
// ---------------------------------------------------------------------------

/** A session summary as returned by GET /sessions and /datasets/{id}/sessions. */
export interface Session {
  id: string
  name: string | null
  dataset_id?: string | null
  dataset_ids?: string[]
  turn_count: number
  first_question: string | null
  created_at?: string | null
  updated_at?: string | null
  [key: string]: unknown
}

/** One turn within a session (GET /sessions/{id} → turns[]). Mirrors /ask. */
export interface TurnView {
  run_id: string
  question: string
  answer_markdown?: string | null
  answer_html?: string | null
  type?: string
  clarification_question?: string | null
  iteration_count?: number
  tokens_input?: number
  tokens_output?: number
  status?: string
  is_best_effort?: boolean
  steps?: AskStep[]
  suggested_questions?: string[]
  dataset_ids?: string[]
  datasets_used?: string[]
  selector_reasoning?: string | null
  prompt_breakdown?: Record<string, unknown>
  created_at?: string | null
  [key: string]: unknown
}

/** Full session detail with its turns (GET /sessions/{id}). */
export interface SessionDetail extends Session {
  turns: TurnView[]
}

// ---------------------------------------------------------------------------
// Memory types (Phase 3 — C29/C31)
// ---------------------------------------------------------------------------

export interface MemoryResponse {
  global_memory: string
  global_memory_facts: string[]
}

// ---------------------------------------------------------------------------
// Endpoint wrappers (Phase 2 surface)
// ---------------------------------------------------------------------------

export const api = {
  health: () => getJson<HealthResponse>('/health'),

  /**
   * POST /upload — multipart `file`, optional `context`, optional `?force=true`.
   * On a duplicate the server returns 409 with code `duplicate_dataset`; this
   * surfaces as an `ApiError` the caller can branch on.
   */
  async upload(
    file: File,
    opts: { context?: string; force?: boolean } = {},
  ): Promise<UploadResponse> {
    const form = new FormData()
    form.append('file', file)
    if (opts.context && opts.context.trim()) {
      form.append('context', opts.context.trim())
    }
    const path = opts.force ? '/upload?force=true' : '/upload'
    const res = await fetch(path, { method: 'POST', body: form })
    return unwrap<UploadResponse>(res)
  },

  listDatasets: () => getJson<DatasetSummary[]>('/datasets'),

  getDataset: (id: string) => getJson<DatasetDetail>(`/datasets/${encodeURIComponent(id)}`),

  preview: (id: string, rows = 10) =>
    getJson<PreviewResponse>(`/datasets/${encodeURIComponent(id)}/preview?rows=${rows}`),

  deleteDataset: (id: string) => del<unknown>(`/datasets/${encodeURIComponent(id)}`),

  /**
   * POST /ask — the analysis entry point (spec/api.md).
   *
   * Body: `{dataset_id? | dataset_ids?, question, session_id?, skip_clarification}`.
   *  - Pass `datasetIds` to pin an explicit set of datasets (C19 selector is
   *    skipped); pass a single `datasetId` for the simple one-dataset case;
   *    omit both to let the server's selector pick over all uploaded datasets.
   *  - Pass `sessionId` to continue a session; omit to start a new one.
   *  - Pass `skipClarification` to bypass the C26 pre-flight (used when a user
   *    re-submits after a clarification turn).
   *
   * Returns either a `type:"answer"` or a `type:"clarification"` AskResponse.
   */
  ask: (args: AskArgs) => {
    const body: Record<string, unknown> = {
      question: args.question,
      skip_clarification: args.skipClarification ?? false,
    }
    if (args.datasetIds && args.datasetIds.length > 0) {
      body.dataset_ids = args.datasetIds
    } else if (args.datasetId) {
      body.dataset_id = args.datasetId
    }
    if (args.sessionId) body.session_id = args.sessionId
    return postJson<AskResponse>('/ask', body)
  },

  currentRun: () => getJson<CurrentRun>('/runs/current'),

  dailyStats: () => getJson<DailyStats>('/stats/daily'),

  // --- Sessions (Phase 3) ---------------------------------------------------

  listSessions: () => getJson<Session[]>('/sessions'),

  getSession: (id: string) => getJson<SessionDetail>(`/sessions/${encodeURIComponent(id)}`),

  renameSession: (id: string, name: string) =>
    patchJson<Session>(`/sessions/${encodeURIComponent(id)}/name`, { name }),

  deleteSession: (id: string) => del<unknown>(`/sessions/${encodeURIComponent(id)}`),

  deleteAllSessions: () => del<unknown>('/sessions'),

  datasetSessions: (datasetId: string) =>
    getJson<Session[]>(`/datasets/${encodeURIComponent(datasetId)}/sessions`),

  // --- Memory (Phase 3 — C29/C31) ------------------------------------------

  getMemory: () => getJson<MemoryResponse>('/memory'),

  patchMemory: (text: string) =>
    patchJson<MemoryResponse>('/memory', { global_memory: text }),
}
