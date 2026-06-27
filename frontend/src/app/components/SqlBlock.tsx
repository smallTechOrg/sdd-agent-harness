// Read-only, monospaced display of the SELECT the agent generated (transparency).
export function SqlBlock({ sql }: { sql: string }) {
  if (!sql) return null
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-gray-700">Generated SQL</h2>
      <pre className="overflow-x-auto rounded-lg border border-gray-200 bg-gray-900 p-4 text-xs leading-relaxed text-gray-100">
        <code>{sql}</code>
      </pre>
    </section>
  )
}
