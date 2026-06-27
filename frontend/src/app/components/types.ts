// Shared types built against spec/api.md.

export interface Column {
  name: string
  type: string
}

export interface Dataset {
  dataset_id: string
  name: string
  row_count: number
  columns: Column[]
}

// chart_spec from /ask, e.g.
// { type: "bar", x: "region", series: [{ region: "West", revenue: 410000 }, ...] }
export interface ChartSpec {
  type: string
  x: string
  series: Array<Record<string, string | number>>
}

export interface Answer {
  question_id: string
  answer_text: string
  chart_spec: ChartSpec | null
  status: string
}

// A single Q&A turn kept in the scrollable history.
export interface Turn {
  question: string
  answer: Answer
}

// Friendly copy for the documented api_error codes.
export function friendlyError(code: string | undefined, fallback: string): string {
  switch (code) {
    case 'BAD_UPLOAD':
      return "Couldn't read that file — please upload a valid CSV."
    case 'LLM_UNAVAILABLE':
      return "Couldn't reach the model — try again."
    case 'COMPUTE_FAILED':
      return 'Something went wrong crunching the numbers — try again.'
    case 'BAD_REQUEST':
      return "That request didn't look right — check your input and try again."
    default:
      return fallback
  }
}
