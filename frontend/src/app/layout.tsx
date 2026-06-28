import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Analysis Agent",
  description: "Upload CSV files and ask natural-language questions about your data",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
