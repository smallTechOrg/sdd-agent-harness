import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Data Analysis Agent',
  description: 'Ask questions about your data — answers computed locally',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-100 text-slate-900 antialiased">{children}</body>
    </html>
  )
}
