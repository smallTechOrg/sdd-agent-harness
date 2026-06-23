'use client'

import { useState } from 'react'
import type { Dataset } from '../lib/api'

interface DatasetListProps {
  datasets: Dataset[]
  loading: boolean
  selectedId: string | null
  onSelect: (dataset: Dataset) => void
}

function SchemaTable({ schema }: { schema: Dataset['schema'] }) {
  return (
    <ul className="mt-2 space-y-1 border-l-2 border-gray-200 pl-3">
      {schema.map(col => (
        <li key={col.name} className="flex items-center justify-between text-xs">
          <span className="font-mono text-gray-700">{col.name}</span>
          <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-gray-500">
            {col.type}
          </span>
        </li>
      ))}
    </ul>
  )
}

function DatasetRow({
  dataset,
  selected,
  onSelect,
}: {
  dataset: Dataset
  selected: boolean
  onSelect: (d: Dataset) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <li
      className={`rounded-lg border p-3 transition ${
        selected ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500' : 'border-gray-200 bg-white'
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect(dataset)}
        aria-pressed={selected}
        className="flex w-full items-center justify-between text-left focus:outline-none"
      >
        <span className="text-sm font-medium text-gray-900">{dataset.name}</span>
        <span className="text-xs text-gray-500">{dataset.row_count.toLocaleString()} rows</span>
      </button>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="mt-1 text-xs text-blue-600 hover:underline focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {open ? 'Hide schema' : `Show schema (${dataset.schema.length} columns)`}
      </button>
      {open && <SchemaTable schema={dataset.schema} />}
    </li>
  )
}

export default function DatasetList({ datasets, loading, selectedId, onSelect }: DatasetListProps) {
  if (loading) {
    return (
      <ul className="space-y-2" aria-busy="true">
        {[0, 1, 2].map(i => (
          <li key={i} className="h-14 animate-pulse rounded-lg bg-gray-100 motion-reduce:animate-none" />
        ))}
      </ul>
    )
  }

  if (datasets.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-sm text-gray-500">
        No datasets yet — upload a CSV or Excel file to begin.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {datasets.map(d => (
        <DatasetRow
          key={d.id}
          dataset={d}
          selected={d.id === selectedId}
          onSelect={onSelect}
        />
      ))}
    </ul>
  )
}
