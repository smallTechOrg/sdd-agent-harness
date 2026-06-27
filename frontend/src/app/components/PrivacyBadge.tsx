// The product's core promise — kept prominent near the top.
export default function PrivacyBadge() {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
      <span aria-hidden className="mt-0.5 text-base leading-none">🔒</span>
      <p>
        <span className="font-semibold">Your data stays on this machine</span>
        {' — only summaries are sent to the model.'}
      </p>
    </div>
  )
}
