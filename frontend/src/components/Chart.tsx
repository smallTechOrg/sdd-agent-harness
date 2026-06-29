'use client'

import { useMemo } from 'react'
import type { ChartSpec, ResultRow } from '@/lib/api'

// A small, dependency-free SVG chart renderer. Works with Next static export +
// React 19 with zero version-compat risk. Renders bar / line / scatter from the
// backend chart spec applied to the answer's aggregate `result` rows.

const WIDTH = 520
const HEIGHT = 280
const PAD = { top: 24, right: 16, bottom: 56, left: 64 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom

const SERIES_COLORS = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#dc2626', '#0891b2']

function toNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function cellLabel(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

interface PreparedPoint {
  xLabel: string
  xIndex: number
  y: number
  series: string
}

function prepare(spec: ChartSpec, rows: ResultRow[]) {
  const xLabels: string[] = []
  const xIndexOf = new Map<string, number>()
  const points: PreparedPoint[] = []
  const seriesSet = new Set<string>()

  for (const row of rows) {
    const y = toNumber(row[spec.y])
    if (y === null) continue
    const xLabel = cellLabel(row[spec.x])
    if (!xIndexOf.has(xLabel)) {
      xIndexOf.set(xLabel, xLabels.length)
      xLabels.push(xLabel)
    }
    const series = spec.series ? cellLabel(row[spec.series]) : spec.y
    seriesSet.add(series)
    points.push({ xLabel, xIndex: xIndexOf.get(xLabel)!, y, series })
  }

  const seriesList = Array.from(seriesSet)
  const ys = points.map(p => p.y)
  const maxY = ys.length ? Math.max(...ys, 0) : 0
  const minY = ys.length ? Math.min(...ys, 0) : 0
  return { xLabels, points, seriesList, maxY, minY }
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return [min]
  const ticks: number[] = []
  for (let i = 0; i <= count; i++) ticks.push(min + ((max - min) * i) / count)
  return ticks
}

function formatTick(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  if (Number.isInteger(v)) return String(v)
  return v.toFixed(2)
}

export function Chart({ spec, rows }: { spec: ChartSpec; rows: ResultRow[] }) {
  const data = useMemo(() => prepare(spec, rows), [spec, rows])

  // Nothing chartable — render nothing (no empty box, no error).
  if (!data.points.length || !data.xLabels.length) return null

  const { xLabels, points, seriesList, maxY, minY } = data
  const yMin = Math.min(minY, 0)
  const yMax = maxY === yMin ? yMin + 1 : maxY
  const yScale = (y: number) => PAD.top + PLOT_H - ((y - yMin) / (yMax - yMin)) * PLOT_H
  const slot = PLOT_W / xLabels.length
  const xCenter = (i: number) => PAD.left + slot * i + slot / 2

  const ticks = niceTicks(yMin, yMax)
  const colorOf = (series: string) =>
    SERIES_COLORS[seriesList.indexOf(series) % SERIES_COLORS.length]

  return (
    <div
      data-testid="answer-chart"
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
    >
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
        {spec.title || 'Chart'}
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={spec.title || `${spec.type} chart of ${spec.y} by ${spec.x}`}
        className="h-auto w-full"
        data-testid="answer-chart-svg"
      >
        {/* Y gridlines + ticks */}
        {ticks.map((t, i) => {
          const y = yScale(t)
          return (
            <g key={i}>
              <line
                x1={PAD.left}
                x2={WIDTH - PAD.right}
                y1={y}
                y2={y}
                stroke="#e5e7eb"
                strokeWidth={1}
              />
              <text x={PAD.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#6b7280">
                {formatTick(t)}
              </text>
            </g>
          )
        })}

        {/* X axis baseline */}
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={yScale(yMin)}
          y2={yScale(yMin)}
          stroke="#9ca3af"
          strokeWidth={1}
        />

        {/* X labels */}
        {xLabels.map((label, i) => (
          <text
            key={i}
            x={xCenter(i)}
            y={HEIGHT - PAD.bottom + 16}
            textAnchor="middle"
            fontSize={10}
            fill="#6b7280"
          >
            {label.length > 12 ? `${label.slice(0, 11)}…` : label}
          </text>
        ))}

        {/* Series rendering */}
        {spec.type === 'bar' && (
          <>
            {(() => {
              const n = Math.max(seriesList.length, 1)
              const groupW = slot * 0.7
              const barW = groupW / n
              return points.map((p, idx) => {
                const si = Math.max(seriesList.indexOf(p.series), 0)
                const x = xCenter(p.xIndex) - groupW / 2 + si * barW
                const y0 = yScale(Math.max(0, yMin))
                const y1 = yScale(p.y)
                const top = Math.min(y0, y1)
                const h = Math.max(Math.abs(y1 - y0), 1)
                return (
                  <rect
                    key={idx}
                    x={x}
                    y={top}
                    width={Math.max(barW - 2, 1)}
                    height={h}
                    fill={colorOf(p.series)}
                    rx={2}
                  >
                    <title>{`${p.series} · ${p.xLabel}: ${p.y}`}</title>
                  </rect>
                )
              })
            })()}
          </>
        )}

        {(spec.type === 'line' || spec.type === 'scatter') &&
          seriesList.map(series => {
            const pts = points
              .filter(p => p.series === series)
              .sort((a, b) => a.xIndex - b.xIndex)
            const color = colorOf(series)
            return (
              <g key={series}>
                {spec.type === 'line' && pts.length > 1 && (
                  <polyline
                    fill="none"
                    stroke={color}
                    strokeWidth={2}
                    points={pts.map(p => `${xCenter(p.xIndex)},${yScale(p.y)}`).join(' ')}
                  />
                )}
                {pts.map((p, idx) => (
                  <circle
                    key={idx}
                    cx={xCenter(p.xIndex)}
                    cy={yScale(p.y)}
                    r={3.5}
                    fill={color}
                  >
                    <title>{`${series} · ${p.xLabel}: ${p.y}`}</title>
                  </circle>
                ))}
              </g>
            )
          })}
      </svg>

      {/* Legend (only when multiple series) */}
      {seriesList.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1" data-testid="answer-chart-legend">
          {seriesList.map(s => (
            <span key={s} className="inline-flex items-center gap-1.5 text-xs text-gray-600">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: colorOf(s) }}
                aria-hidden
              />
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
