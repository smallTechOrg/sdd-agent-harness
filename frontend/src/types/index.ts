export interface ColumnProfile {
  name: string
  dtype: string
  null_count: number
  sample_values: unknown[]
}

export interface FileProfile {
  columns: ColumnProfile[]
  row_count: number
  column_count: number
  file_size_bytes: number
  profiled_at: string
}

export interface UploadedFileInfo {
  file_id: string
  original_filename: string
  profile?: FileProfile
  row_count: number
  column_count: number
  created_at?: string
  file_size_bytes?: number
}

export interface ExecutionStep {
  iteration: number
  code: string
  stdout: string
  stderr: string
  success: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  steps?: ExecutionStep[]
  chart?: { data: unknown[]; layout: Record<string, unknown> }
  costInfo?: { input_tokens: number; output_tokens: number; cost_usd: number }
  isStreaming?: boolean
  error?: string
  clarification?: string
}
