import { ComingSoonPill } from './ComingSoon'

// Non-functional, clearly-labelled stubs for features that arrive in later phases.
// Rendered with muted styling + a "Coming soon" pill so they read as intentional
// future work, never as bugs.

// Upload CSV (real in Phase 2) + dataset switcher (real in Phase 3).
export function DataSourceBar() {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-gray-500" htmlFor="dataset">
          Dataset
        </label>
        <select
          id="dataset"
          disabled
          aria-label="Dataset switcher (coming soon)"
          className="cursor-not-allowed rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-500 opacity-70"
        >
          <option>Sample sales data</option>
        </select>
        <ComingSoonPill />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="cursor-not-allowed rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-500 opacity-70"
        >
          Upload CSV
        </button>
        <ComingSoonPill />
      </div>
    </div>
  )
}

// Saved dashboards placeholder panel.
export function SavedDashboards() {
  return (
    <section className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-gray-500">Saved dashboards</h2>
        <ComingSoonPill />
      </div>
      <p className="mt-2 text-sm text-gray-400">
        Pin questions and charts you want to revisit. This panel becomes
        functional in a later phase.
      </p>
    </section>
  )
}
