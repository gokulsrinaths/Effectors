'use client'

import { useEffect, useRef, useState } from 'react'

interface Props {
  queryPdbUrl: string
  matchPdbUrl: string
  matchId: string
  accessToken: string
}

declare global {
  interface Window {
    $3Dmol: any
  }
}

export default function StructureViewer({ queryPdbUrl, matchPdbUrl, matchId, accessToken }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError]   = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false

    const load3Dmol = () =>
      new Promise<void>((resolve, reject) => {
        if (window.$3Dmol) { resolve(); return }
        const script = document.createElement('script')
        script.src = 'https://3Dmol.org/build/3Dmol-min.js'
        script.onload = () => resolve()
        script.onerror = () => reject(new Error('Failed to load 3Dmol.js'))
        document.head.appendChild(script)
      })

    const fetchPdb = async (url: string) => {
      const r = await fetch(url, {
        headers: accessToken ? { 'x-job-token': accessToken } : {},
      })
      if (!r.ok) throw new Error(`HTTP ${r.status} fetching ${url}`)
      return r.text()
    }

    const init = async () => {
      try {
        await load3Dmol()
        const [queryPdb, matchPdb] = await Promise.all([
          fetchPdb(queryPdbUrl),
          fetchPdb(matchPdbUrl),
        ])
        if (cancelled || !containerRef.current) return

        const viewer = window.$3Dmol.createViewer(containerRef.current, {
          backgroundColor: '#0d1526',
        })
        viewer.addModel(queryPdb, 'pdb')
        viewer.setStyle({ model: 0 }, { cartoon: { color: '#00d4ff' } })
        viewer.addModel(matchPdb, 'pdb')
        viewer.setStyle({ model: 1 }, { cartoon: { color: '#f0a000' } })
        viewer.zoomTo()
        viewer.render()
        if (!cancelled) setLoaded(true)
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Viewer error')
      }
    }

    init()
    return () => { cancelled = true }
  }, [queryPdbUrl, matchPdbUrl, accessToken])

  if (error) return (
    <div style={{ padding: '12px 16px', color: '#ff6666', fontSize: '0.8rem', background: 'rgba(255,100,100,0.08)', borderRadius: 6 }}>
      3D viewer unavailable: {error}
    </div>
  )

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 8, fontSize: '0.75rem', color: '#8899aa' }}>
        <span><span style={{ color: '#00d4ff' }}>■</span> Query structure</span>
        <span><span style={{ color: '#f0a000' }}>■</span> Best match: {matchId}</span>
        {!loaded && <span style={{ color: '#8899aa' }}>Loading viewer…</span>}
      </div>
      <div
        ref={containerRef}
        style={{ position: 'relative', width: '100%', height: 380, borderRadius: 8, border: '1px solid rgba(99,210,255,0.12)', overflow: 'hidden' }}
      />
    </div>
  )
}
