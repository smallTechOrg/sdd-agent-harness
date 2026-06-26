import type { Metadata } from 'next'
import './globals.css'
import { StubNavLink } from '@/components/StubNavLink'

export const metadata: Metadata = {
  title: 'Data Analysis Agent',
  description: 'Upload a CSV and ask natural-language questions',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <header className="border-b border-gray-200 bg-white px-6 py-3 flex items-center justify-between">
          <span className="font-semibold text-gray-800">Data Analysis Agent</span>
          <nav className="flex items-center gap-4 text-sm">
            <StubNavLink
              label="Dashboard"
              phase="Phase 2"
              message="Coming soon — a dashboard for pinned charts is planned for Phase 2."
            />
            <StubNavLink
              label="Sign in"
              phase="Phase 3"
              message="Coming soon — user accounts are planned for a future release."
            />
          </nav>
        </header>
        {children}
      </body>
    </html>
  )
}
