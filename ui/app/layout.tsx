import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DataChat",
  description: "Chat with your data — upload CSV/JSON, ask in natural language, get grounded answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
