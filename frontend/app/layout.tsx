import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Structure-based Effector Discovery Platform',
  description: 'Research-grade platform for structure-based effector discovery',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}

