// Shared types + parsing for the Analysis Console.
// The backend returns the envelope { data: {...}, error } where data.output_text
// is a JSON STRING that decodes to AnalysisPayload (see spec/api.md).

export type ChartType = 'bar' | 'line' | 'pie' | 'scatter' | 'table'

export interface ChartSpec {
  chart_type: ChartType
  x: string
  y: string[]
}

export interface AnalysisPayload {
  sql: string
  columns: string[]
  rows: unknown[][]
  chart_spec: ChartSpec | null
  error: string | null
}

export interface RunData {
  run_id?: string
  status?: string
  output_text?: string | null
  error?: string | null
}

export interface RunEnvelope {
  data?: RunData | null
  error?: string | null
}

const EMPTY_PAYLOAD: AnalysisPayload = {
  sql: '',
  columns: [],
  rows: [],
  chart_spec: null,
  error: null,
}

/**
 * Decode the run envelope into a render-ready AnalysisPayload.
 * Always returns a consistent shape and never throws:
 *  - parses data.output_text JSON when present/valid
 *  - falls back to the top-level data.error when output_text is missing/unparseable
 */
export function parseRunEnvelope(envelope: RunEnvelope | null | undefined): AnalysisPayload {
  const data = envelope?.data ?? null
  const topError = data?.error ?? envelope?.error ?? null

  const raw = data?.output_text
  if (typeof raw === 'string' && raw.trim() !== '') {
    try {
      const parsed = JSON.parse(raw) as Partial<AnalysisPayload>
      return {
        sql: typeof parsed.sql === 'string' ? parsed.sql : '',
        columns: Array.isArray(parsed.columns) ? parsed.columns.map(String) : [],
        rows: Array.isArray(parsed.rows) ? (parsed.rows as unknown[][]) : [],
        chart_spec: isValidChartSpec(parsed.chart_spec) ? parsed.chart_spec : null,
        error:
          typeof parsed.error === 'string' && parsed.error.trim() !== ''
            ? parsed.error
            : topError,
      }
    } catch {
      // Unparseable payload — fall through to the top-level error.
    }
  }

  return {
    ...EMPTY_PAYLOAD,
    error: topError ?? 'The server returned an unreadable response.',
  }
}

function isValidChartSpec(spec: unknown): spec is ChartSpec {
  if (!spec || typeof spec !== 'object') return false
  const s = spec as Record<string, unknown>
  const validTypes: ChartType[] = ['bar', 'line', 'pie', 'scatter', 'table']
  return (
    typeof s.chart_type === 'string' &&
    (validTypes as string[]).includes(s.chart_type) &&
    typeof s.x === 'string' &&
    Array.isArray(s.y) &&
    s.y.every(item => typeof item === 'string')
  )
}

/**
 * Zip columns + rows into the array-of-objects shape Recharts expects.
 * Numeric-looking cells are coerced to numbers so chart axes scale correctly.
 */
export function rowsToObjects(
  columns: string[],
  rows: unknown[][],
): Record<string, unknown>[] {
  return rows.map(row => {
    const obj: Record<string, unknown> = {}
    columns.forEach((col, idx) => {
      obj[col] = row[idx]
    })
    return obj
  })
}

export function coerceNumber(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : 0
}
