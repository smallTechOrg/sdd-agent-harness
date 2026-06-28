'use client'
import { useEffect, useRef } from 'react'

interface PlotlyChartProps {
  plotlySpec: { data: unknown[]; layout: Record<string, unknown> }
}

export default function PlotlyChart({ plotlySpec }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    if (!plotlySpec.data || plotlySpec.data.length === 0) return

    let cancelled = false
    import('plotly.js-dist-min').then((Plotly) => {
      if (cancelled || !containerRef.current) return
      Plotly.newPlot(
        containerRef.current,
        plotlySpec.data as Plotly.Data[],
        { ...plotlySpec.layout, responsive: true } as unknown as Plotly.Layout,
        { displayModeBar: false, responsive: true }
      )
    }).catch(console.error)

    return () => {
      cancelled = true
      if (containerRef.current) {
        import('plotly.js-dist-min').then((Plotly) => {
          if (containerRef.current) Plotly.purge(containerRef.current)
        }).catch(() => {})
      }
    }
  }, [plotlySpec])

  if (!plotlySpec.data || plotlySpec.data.length === 0) return null

  return (
    <div
      ref={containerRef}
      className="w-full mt-3 rounded-lg overflow-hidden"
      style={{ minHeight: '300px' }}
      data-testid="plotly-chart"
    />
  )
}
