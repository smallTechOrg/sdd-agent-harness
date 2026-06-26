'use client'

/**
 * <StubBanner provider /> : the yellow "stub mode" banner. Driven by GET
 * /health's `provider`: shown ONLY when the backend runs in stub mode (no API
 * key) so canned answers are never mistaken for real output.
 */

export function StubBanner({ provider }: { provider?: string | null }) {
  // While health is loading, `provider` is undefined — render nothing (no
  // flash of a banner that may not apply). In real (gemini/openrouter) mode,
  // render nothing. Only the stub provider gets the yellow banner.
  if (provider !== 'stub') return null

  return (
    <div
      role="status"
      className="border-b border-yellow-300 bg-yellow-100 px-4 py-2 text-center text-sm text-yellow-900"
    >
      <span className="font-semibold">Stub mode</span> — no LLM API key is set, so
      the agent returns plausible canned answers and runs fully offline. Add{' '}
      <code className="rounded bg-yellow-200/70 px-1 py-0.5 text-xs">
        AGENT_GEMINI_API_KEY
      </code>{' '}
      to <code className="rounded bg-yellow-200/70 px-1 py-0.5 text-xs">.env</code> for
      real analysis.
    </div>
  )
}
