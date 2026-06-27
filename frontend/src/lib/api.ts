// Thin API client for the DataChat backend.
// All responses use the ok(data) / api_error envelope from spec/api.md:
//   success -> { "data": ..., "error": null }
//   failure -> HTTP error with { "detail": { "code", "message" } }
//
// Paths are same-origin relative ("/datasets", "/chat"): the FastAPI server
// serves both the static /app UI and the API. Note basePath '/app' applies to
// Next.js routing/assets only, NOT to fetch() URLs, so these stay un-prefixed.

import type { ChatResponse, Dataset } from './types'

export class ApiError extends Error {
  code: string
  status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function parseError(res: Response, fallback: string): Promise<ApiError> {
  let message = fallback
  let code = 'UNKNOWN'
  try {
    const body = await res.json()
    if (body?.detail?.message) message = body.detail.message
    if (body?.detail?.code) code = body.detail.code
  } catch {
    // non-JSON error body — keep the fallback message
  }
  return new ApiError(message, code, res.status)
}

export async function uploadDataset(file: File): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/datasets', { method: 'POST', body: form })
  if (!res.ok) {
    throw await parseError(
      res,
      "Couldn't read that file — please upload a CSV or .xlsx",
    )
  }
  const body = await res.json()
  return body.data as Dataset
}

export interface AskParams {
  datasetId: string
  question: string
  conversationId?: string
}

export async function askQuestion(params: AskParams): Promise<ChatResponse> {
  const payload: Record<string, string> = {
    dataset_id: params.datasetId,
    question: params.question,
  }
  if (params.conversationId) payload.conversation_id = params.conversationId

  const res = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw await parseError(res, "I couldn't answer that — try rephrasing")
  }
  const body = await res.json()
  return body.data as ChatResponse
}
