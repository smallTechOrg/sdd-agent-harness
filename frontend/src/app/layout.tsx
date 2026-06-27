import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'DataChat',
  description:
    'Upload a CSV and ask questions about it in plain English — your data stays on your machine.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  )
}
