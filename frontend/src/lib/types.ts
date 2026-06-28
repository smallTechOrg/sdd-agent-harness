// Shared types mirroring the spec/api.md contract (Pandora Phase 1).

export interface ColumnProfile {
  name: string
  dtype: string
  missing_pct: number
  min?: number | string | null
  max?: number | string | null
  distinct_count?: number | null
  example_labels?: string[] | null
}

export interface QualityFlag {
  column: string
  issue: string
}

export interface DatasetProfile {
  columns: ColumnProfile[]
  quality_flags?: QualityFlag[]
  // Some backends nest row/column counts here too; the top-level fields are canonical.
  row_count?: number
  column_count?: number
}

export interface DatasetResponse {
  dataset_id: string
  filename: string
  row_count: number
  column_count: number
  profile: DatasetProfile
  suggested_questions: string[]
  status?: string
}

export interface ChartSpec {
  type: 'bar' | 'line' | 'pie' | string
  x?: string
  y?: string | string[]
  series?: string | null
}

export interface SummaryTable {
  columns: string[]
  rows: Array<Array<string | number | null>>
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
}

export interface AnswerEvent {
  question_id: string
  answer_text: string
  chart_spec: ChartSpec | null
  summary_table: SummaryTable | null
  code: string
  usage: Usage
  daily_total_usd: number
  status: 'completed'
}

export interface ErrorEvent {
  question_id?: string
  message: string
  code_attempted?: string
  status: 'stuck'
}

export interface StepEvent {
  step: string
  index: number
  elapsed_ms: number
}
