'use client'

interface Props {
  queryPdbUrl: string
  matchPdbUrl: string
  matchId: string
  accessToken: string
}

export default function StructureViewer({ queryPdbUrl, matchPdbUrl, matchId, accessToken }: Props) {
  const src =
    `/viewer.html` +
    `?queryUrl=${encodeURIComponent(queryPdbUrl)}` +
    `&matchUrl=${encodeURIComponent(matchPdbUrl)}` +
    `&token=${encodeURIComponent(accessToken)}`

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 8, fontSize: '0.75rem', color: '#8899aa' }}>
        <span><span style={{ color: '#00d4ff' }}>■</span> Query structure</span>
        <span><span style={{ color: '#f0a000' }}>■</span> Best match: {matchId}</span>
      </div>
      <iframe
        src={src}
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
