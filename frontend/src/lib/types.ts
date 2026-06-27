// Shared types mirroring the API contract in spec/api.md.

export interface SchemaColumn {
  name: string
  dtype: string
}

export interface DatasetSchema {
  columns: SchemaColumn[]
}

export interface Dataset {
  dataset_id: string
  filename: string
  file_type: string
  row_count: number
  schema: DatasetSchema
}

export type ChartType = 'bar' | 'line' | 'pie'

export interface ChartSeries {
  name: string
  values: number[]
}

export interface ChartSpec {
  type: ChartType
  title: string
  labels: string[]
  series: ChartSeries[]
}

export interface ChatResponse {
  conversation_id: string
  answer: string
  chart: ChartSpec | null
}

export type MessageRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  chart: ChartSpec | null
  // UI-only flags
  pending?: boolean
  isError?: boolean
}
