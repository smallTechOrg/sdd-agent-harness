/**
 * API contract (per spec/api.md). All responses use the envelope
 * `{ "data": ..., "error": null }`; errors carry `{ "detail": { code, message } }`.
 *
 * SINGLE-ORIGIN: the frontend is a static export mounted by FastAPI at `/app`,
 * while the API routes live at the server root. fetch() must therefore use
 * absolute, root-relative paths like `/datasets` (which resolve to
 * `http://localhost:8001/datasets`) — NOT `/app/datasets`, and NOT a hardcoded
 * `http://localhost:3000/...` origin.
 */

export interface Dataset {
  dataset_id: string
  filename: string
  file_format: string
  row_count: number
  column_count: number
  columns: string[]
  status: string
}

export interface Analysis {
  analysis_id: string
  dataset_id: string
  question: string
  status: string
  answer: string
  code: string
  steps: string
  result_value: string
  attempts: number
}

interface Envelope<T> {
  data: T | null
  error: unknown
}

interface ErrorBody {
  detail?: { code?: string; message?: string }
}

/** Extracts a human-readable message from a failed response, with a sane fallback. */
async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as ErrorBody
    const message = body?.detail?.message
    if (message) return message
  } catch {
    // fall through to the generic message
  }
  return `Request failed (${res.status})`
}

export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/datasets', { method: 'POST', body: form })
  if (!res.ok) {
    throw new Error(await readError(res))
  }
  const body = (await res.json()) as Envelope<Dataset>
  if (!body.data) {
    throw new Error('The server returned an empty response.')
  }
  return body.data
}

export async function runAnalysis(datasetId: string, question: string): Promise<Analysis> {
  const res = await fetch('/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, question }),
  })
  if (!res.ok) {
    throw new Error(await readError(res))
  }
  const body = (await res.json()) as Envelope<Analysis>
  if (!body.data) {
    throw new Error('The server returned an empty response.')
  }
  return body.data
}
