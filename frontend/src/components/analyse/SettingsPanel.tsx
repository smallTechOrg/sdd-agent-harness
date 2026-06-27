'use client'

import { useEffect, useState } from 'react'
import { api, type SettingsData } from '@/lib/api'

interface ModelEntry {
  value: string
  label: string
  /** USD per 1M input tokens — null means unknown */
  input: number | null
  /** USD per 1M output tokens — null means unknown */
  output: number | null
}

/** Known models with verified / published pricing (USD per 1M tokens). */
const LLM_MODELS: ModelEntry[] = [
  // ── Gemini ──────────────────────────────────────────────────────────────
  { value: 'gemini-2.5-pro',           label: 'Gemini 2.5 Pro',           input: 1.25,  output: 10.00 },
  { value: 'gemini-2.5-flash',         label: 'Gemini 2.5 Flash',         input: 0.15,  output: 0.60  },
  { value: 'gemini-2.5-flash-lite',    label: 'Gemini 2.5 Flash Lite',    input: 0.075, output: 0.30  },
  { value: 'gemini-2.0-flash',         label: 'Gemini 2.0 Flash',         input: 0.10,  output: 0.40  },
  { value: 'gemini-2.0-flash-lite',    label: 'Gemini 2.0 Flash Lite',    input: 0.075, output: 0.30  },
  { value: 'gemini-1.5-pro',           label: 'Gemini 1.5 Pro',           input: 1.25,  output: 5.00  },
  { value: 'gemini-1.5-flash',         label: 'Gemini 1.5 Flash',         input: 0.075, output: 0.30  },
  { value: 'gemini-1.5-flash-8b',      label: 'Gemini 1.5 Flash 8B',      input: 0.0375,output: 0.15  },
  { value: 'gemini-3.1-flash-lite',    label: 'Gemini 3.1 Flash Lite (default)', input: null, output: null },
  // ── Claude (Anthropic provider) ─────────────────────────────────────────
  { value: 'claude-opus-4-8',           label: 'Claude Opus 4.8',          input: 15.00, output: 75.00 },
  { value: 'claude-sonnet-4-6',         label: 'Claude Sonnet 4.6',        input: 3.00,  output: 15.00 },
  { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',         input: 0.80,  output: 4.00  },
]

const PRICE_LOOKUP: Record<string, { input: number; output: number }> = {}
for (const m of LLM_MODELS) {
  if (m.input !== null && m.output !== null) {
    PRICE_LOOKUP[m.value] = { input: m.input, output: m.output }
  }
}

export function SettingsPanel({
  open,
  onClose,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  onSaved?: () => void
}) {
  const [form, setForm] = useState<SettingsData>({
    llm_model: null,
    max_iterations: null,
    price_input_per_million: null,
    price_output_per_million: null,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [priceAutoFilled, setPriceAutoFilled] = useState(false)

  useEffect(() => {
    if (!open) return
    api.getSettings().then(data => setForm(data)).catch(() => {})
  }, [open])

  if (!open) return null

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const modelVal = e.target.value || null
    const known = modelVal ? PRICE_LOOKUP[modelVal] : undefined
    if (known) {
      setForm(prev => ({
        ...prev,
        llm_model: modelVal,
        price_input_per_million: String(known.input),
        price_output_per_million: String(known.output),
      }))
      setPriceAutoFilled(true)
    } else {
      setForm(prev => ({ ...prev, llm_model: modelVal }))
      setPriceAutoFilled(false)
    }
  }

  const handlePriceChange = (key: 'price_input_per_million' | 'price_output_per_million') =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setPriceAutoFilled(false)
      setForm(prev => ({ ...prev, [key]: e.target.value || null }))
    }

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.patchSettings(form)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      onSaved?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const activeModel = LLM_MODELS.find(m => m.value === (form.llm_model ?? ''))
  const showUnknownPrice = activeModel && activeModel.input === null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Settings</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={save} className="space-y-4">
          {/* LLM Model */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">LLM Model</label>
            <select
              value={form.llm_model ?? ''}
              onChange={handleModelChange}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Default (env)</option>
              <optgroup label="Gemini">
                {LLM_MODELS.filter(m => m.value.startsWith('gemini')).map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </optgroup>
              <optgroup label="Claude (Anthropic)">
                {LLM_MODELS.filter(m => m.value.startsWith('claude')).map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </optgroup>
            </select>
            <p className="mt-1 text-[11px] text-gray-400">
              Leave &quot;Default&quot; to use AGENT_LLM_MODEL env var.
            </p>
          </div>

          {/* Max Iterations */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">Max iterations</label>
            <input
              type="number"
              min={1}
              max={20}
              value={form.max_iterations ?? ''}
              onChange={e => setForm(prev => ({ ...prev, max_iterations: e.target.value || null }))}
              placeholder="Default (env)"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Pricing — auto-filled from model selection */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-medium text-gray-700">Token pricing (USD per 1M tokens)</p>
              {priceAutoFilled && (
                <span className="text-[10px] font-medium text-green-600">auto-filled</span>
              )}
            </div>
            {showUnknownPrice && (
              <p className="mb-2 text-[11px] text-amber-600">
                No published price for this model — enter manually or leave blank for N/A.
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[11px] text-gray-500">Input / prompt</label>
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={form.price_input_per_million ?? ''}
                  onChange={handlePriceChange('price_input_per_million')}
                  placeholder="e.g. 0.075"
                  className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] text-gray-500">Output / completion</label>
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={form.price_output_per_million ?? ''}
                  onChange={handlePriceChange('price_output_per_million')}
                  placeholder="e.g. 0.30"
                  className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saved ? 'Saved!' : saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
