import { NextResponse } from 'next/server'

export const runtime = 'nodejs'

function escapeXml(s: string) {
  return s.replace(/[<>&"]/g, (c) => {
    switch (c) {
      case '<':
        return '&lt;'
      case '>':
        return '&gt;'
      case '&':
        return '&amp;'
      case '"':
        return '&quot;'
      default:
        return c
    }
  })
}

export async function GET(
  _req: Request,
  { params }: { params: { id: string } }
) {
  const id = decodeURIComponent(params.id || 'demo')
  const title = escapeXml(id)

  // Simple inline SVG “structure” placeholder for demos.
  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#2563eb"/>
      <stop offset="1" stop-color="#22c55e"/>
    </linearGradient>
    <filter id="s" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#0f172a" flood-opacity="0.25"/>
    </filter>
  </defs>

  <rect x="30" y="30" width="840" height="460" rx="16" fill="#ffffff" filter="url(#s)"/>
  <rect x="30" y="30" width="840" height="72" rx="16" fill="#0b1220"/>
  <text x="60" y="76" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI" font-size="22" fill="#e2e8f0">
    Demo Visualization
  </text>
  <text x="60" y="130" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI" font-size="18" fill="#0f172a">
    Best Match: ${title}
  </text>

  <path d="M120 370 C 220 180, 320 460, 420 280 S 620 120, 760 320"
        fill="none" stroke="url(#g)" stroke-width="18" stroke-linecap="round"/>
  <circle cx="120" cy="370" r="10" fill="#2563eb"/>
  <circle cx="420" cy="280" r="10" fill="#16a34a"/>
  <circle cx="760" cy="320" r="10" fill="#22c55e"/>

  <g opacity="0.9">
    <text x="60" y="170" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono" font-size="14" fill="#475569">
      Rendered placeholder (mock) • Replace with real ChimeraX/py3Dmol output when available
    </text>
  </g>
</svg>`

  return new NextResponse(svg, {
    headers: {
      'Content-Type': 'image/svg+xml; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  })
}

