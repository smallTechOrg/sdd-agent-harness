// Labelled, NON-FUNCTIONAL placeholders for later phases.
// Deliberately muted + disabled + badged so they read as "the vision", never as bugs.

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
      {children}
    </span>
  )
}

function Stub({
  title,
  phase,
  children,
}: {
  title: string
  phase: string
  children: React.ReactNode
}) {
  return (
    <div className="select-none rounded-lg border border-dashed border-gray-200 bg-gray-50 p-3 opacity-70">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        <Badge>{phase}</Badge>
      </div>
      <div className="pointer-events-none cursor-not-allowed">{children}</div>
    </div>
  )
}

export default function ComingSoon() {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-500">More features</h2>
      <p className="mb-4 text-xs text-gray-400">Previewing what&rsquo;s next — these are not active yet.</p>

      <div className="space-y-3">
        <Stub title="Connect PostgreSQL" phase="Coming soon · Phase 2">
          <input
            disabled
            placeholder="postgresql://user:pass@host/db"
            className="mb-2 w-full rounded-md border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-400"
          />
          <button disabled className="rounded-md bg-gray-300 px-3 py-1.5 text-xs font-medium text-white">
            Connect
          </button>
        </Stub>

        <Stub title="Switch dataset" phase="Coming soon">
          <select disabled className="w-full rounded-md border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-400">
            <option>Multiple datasets arrive later…</option>
          </select>
        </Stub>

        <Stub title="Download report" phase="Coming soon · Phase 3">
          <button disabled className="w-full rounded-md bg-gray-300 px-3 py-1.5 text-xs font-medium text-white">
            Download HTML report
          </button>
        </Stub>

        <Stub title="Detect anomalies" phase="Coming soon · Phase 5">
          <button disabled className="w-full rounded-md bg-gray-300 px-3 py-1.5 text-xs font-medium text-white">
            Scan for anomalies
          </button>
        </Stub>
      </div>
    </section>
  )
}
