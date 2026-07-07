'use client'

import { useEffect, useRef, useState } from 'react'

interface Props {
  queryPdbUrl: string
  matchPdbUrl: string
  matchId: string
  accessToken: string
}

export default function StructureViewer({ queryPdbUrl, matchPdbUrl, matchId, accessToken }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false

    async function fetchAndSend() {
      try {
        setStatus('loading')

        // Fetch both PDB files as text (blob URLs work fine here in parent context)
        const headers: Record<string, string> = accessToken ? { 'x-job-token': accessToken } : {}
        const [queryText, matchText] = await Promise.all([
          fetch(queryPdbUrl, { headers }).then(r => { if (!r.ok) throw new Error('query fetch failed'); return r.text() }),
          fetch(matchPdbUrl, { headers }).then(r => { if (!r.ok) throw new Error('match fetch failed'); return r.text() }),
        ])

        if (cancelled) return

        // Wait for iframe to load, then postMessage the PDB content
        const iframe = iframeRef.current
        if (!iframe) return

        const send = () => {
          iframe.contentWindow?.postMessage({ queryPdb: queryText, matchPdb: matchText }, '*')
          setStatus('ready')
        }

        if (iframe.contentDocument?.readyState === 'complete') {
          send()
        } else {
          iframe.onload = send
        }
      } catch (e: any) {
        if (!cancelled) setStatus('error')
      }
    }

    fetchAndSend()
    return () => { cancelled = true }
  }, [queryPdbUrl, matchPdbUrl, accessToken])

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 8, fontSize: '0.75rem', color: '#8899aa' }}>
        <span><span style={{ color: '#00d4ff' }}>■</span> Query structure</span>
        <span><span style={{ color: '#f0a000' }}>■</span> Best match: {matchId}</span>
        {status === 'loading' && <span style={{ color: '#8899aa' }}>Loading viewer…</span>}
        {status === 'error' && <span style={{ color: '#ff6666' }}>Failed to load structures</span>}
      </div>
      <iframe
        ref={iframeRef}
        src="/viewer.html"
        style={{
          width: '100%',
          height: 380,
          border: '1px solid rgba(99,210,255,0.12)',
          borderRadius: 8,
          display: 'block',
        }}
        title="3D structure viewer"
      />
    </div>
  )
}
