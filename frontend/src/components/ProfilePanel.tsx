'use client'
import { FileProfile } from '@/types'

interface Props { profile: FileProfile; filename: string }

export default function ProfilePanel({ profile, filename }: Props) {
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mt-3 text-sm">
      <p className="font-semibold text-blue-800 mb-2">{filename} — {profile.row_count.toLocaleString()} rows × {profile.column_count} columns</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-blue-100">
              <th className="text-left p-1 border border-blue-200">Column</th>
              <th className="text-left p-1 border border-blue-200">Type</th>
              <th className="text-right p-1 border border-blue-200">Nulls</th>
              <th className="text-left p-1 border border-blue-200">Sample values</th>
            </tr>
          </thead>
          <tbody>
            {profile.columns.map((col) => (
              <tr key={col.name} className="even:bg-blue-50">
                <td className="p-1 border border-blue-200 font-mono">{col.name}</td>
                <td className="p-1 border border-blue-200 text-gray-500">{col.dtype}</td>
                <td className="p-1 border border-blue-200 text-right">{col.null_count}</td>
                <td className="p-1 border border-blue-200 text-gray-600">
                  {col.sample_values.slice(0, 3).map(String).join(', ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
