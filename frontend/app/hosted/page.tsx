'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import styles from './page.module.css'
import dynamic from 'next/dynamic'

const StructureViewer = dynamic(() => import('./StructureViewer'), { ssr: false })

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

type JobStatus = 'queued' | 'reserved' | 'submitted' | 'running' | 'completed' | 'failed'

interface HostedJob {
  id: string
  input_type: string
  email?: string | null
  status: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  summary?: Record<string, unknown> | null
  error_message?: string | null
  backend_mode: string
  has_result: boolean
  poll_path: string
  result_path?: string | null
  access_token?: string | null
  remote_job_id?: string | null
}

interface TmMatch {
  structure: string
  tm_score: number
  rmsd: number
  aligned_length: number
}

interface HostedResult {
  processing_result?: {
    results?: Array<{
      query_id?: string
      blast_result?: { e_value?: number; identity?: number; hit_id?: string }
      tm_align_result?: { tm_score?: number; rmsd?: number; top_matches?: TmMatch[] }
      classification?: string
      best_match_id?: string
    }>
  }
  summary?: Record<string, unknown>
  alphafold?: { status?: string; pdb_local_path?: string }
  structure_image_path?: string
  structure_image_local_path?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function statusClass(s: string) {
  if (s === 'queued')    return styles.statusQueued
  if (s === 'submitted') return styles.statusSubmitted
  if (s === 'running')   return styles.statusRunning
  if (s === 'completed') return styles.statusCompleted
  return styles.statusFailed
}

function statusDotColor(s: string) {
  if (s === 'queued')    return '#8899aa'
  if (s === 'submitted') return '#f0a000'
  if (s === 'running')   return '#00d4ff'
  if (s === 'completed') return '#00c864'
  return '#ff4444'
}

function classificationStyle(c?: string) {
  if (!c) return ''
  if (c.toLowerCase().includes('known') || c.toLowerCase().includes('already')) return styles.classKnown
  if (c.toLowerCase().includes('similar')) return styles.classSimilar
  return styles.classNovel
}

function tmScoreColor(score?: number) {
  if (score == null) return ''
  if (score >= 0.5) return styles.metricGreen
  if (score >= 0.3) return styles.metricYellow
  return styles.metricRed
}

function fmt(v: unknown, decimals = 3): string {
  if (v == null) return '—'
  if (typeof v === 'number') return v.toFixed(decimals)
  return String(v)
}

function fmtEval(v?: number): string {
  if (v == null) return '—'
  return v.toExponential(2)
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function HostedPage() {
  const [mounted, setMounted]         = useState(false)
  const [activeTab, setActiveTab]     = useState<'sequence' | 'upload'>('sequence')
  const [email, setEmail]             = useState('')
  const [sequenceId, setSequenceId]   = useState('')
  const [sequence, setSequence]       = useState('')
  const [uploadType, setUploadType]   = useState<'structure' | 'fasta'>('structure')
  const [uploadFile, setUploadFile]   = useState<File | null>(null)
  const [job, setJob]                 = useState<HostedJob | null>(null)
  const [result, setResult]           = useState<HostedResult | null>(null)
  const [accessToken, setAccessToken] = useState('')
  const [message, setMessage]         = useState('')
  const [submitting, setSubmitting]   = useState(false)
  const [modeInfo, setModeInfo]       = useState<Record<string, unknown> | null>(null)
  const [runAlphafold, setRunAlphafold] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [structureImgUrl, setStructureImgUrl] = useState<string | null>(null)
  const [queryPdbUrl, setQueryPdbUrl]   = useState<string | null>(null)
  const [rawOpen, setRawOpen]         = useState(false)
  const [elapsedSecs, setElapsedSecs] = useState(0)
  const [lastPayload, setLastPayload] = useState<Record<string, unknown> | null>(null)
  const pollCountRef = useRef(0)
  const startTimeRef = useRef(0)
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setMounted(true)
    // Override body background for dark theme (globals.css sets white)
    const prev = document.body.style.backgroundColor
    document.body.style.backgroundColor = '#0a0e1a'
    return () => { document.body.style.backgroundColor = prev }
  }, [])

  const jobIsTerminal = useMemo(
    () => job?.status === 'completed' || job?.status === 'failed',
    [job]
  )

  useEffect(() => {
    axios.get(`${API_BASE_URL}/jobs/mode`).then(r => setModeInfo(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (!job || jobIsTerminal) return
    pollCountRef.current = 0
    startTimeRef.current = Date.now()

    const schedulePoll = () => {
      // Exponential backoff: 3s → 6s → 12s → 24s → cap at 30s
      const delay = Math.min(3000 * Math.pow(2, Math.floor(pollCountRef.current / 3)), 30000)
      pollTimerRef.current = setTimeout(doPoll, delay)
    }

    const doPoll = async () => {
      setElapsedSecs(Math.floor((Date.now() - startTimeRef.current) / 1000))
      try {
        const r = await axios.get<HostedJob>(`${API_BASE_URL}${job.poll_path}`, {
          headers: accessToken ? { 'x-job-token': accessToken } : undefined,
        })
        pollCountRef.current += 1
        setJob(r.data)
        if (r.data.status === 'completed' && r.data.result_path) {
          const rr = await axios.get<HostedResult>(`${API_BASE_URL}${r.data.result_path}`, {
            headers: accessToken ? { 'x-job-token': accessToken } : undefined,
          })
          setResult(rr.data)
          setMessage('Job completed successfully.')
          axios.get(`${API_BASE_URL}/jobs/files/${r.data.id}/structure-image`, {
            headers: { 'x-job-token': accessToken },
            responseType: 'blob',
          }).then(imgR => setStructureImgUrl(URL.createObjectURL(imgR.data))).catch(() => {})
          if (rr.data?.alphafold?.pdb_local_path) {
            axios.get(`${API_BASE_URL}/jobs/files/${r.data.id}/alphafold`, {
              headers: { 'x-job-token': accessToken },
              responseType: 'blob',
            }).then(pdbR => setQueryPdbUrl(URL.createObjectURL(pdbR.data))).catch(() => {})
          } else if (uploadFile && uploadType === 'structure') {
            setQueryPdbUrl(URL.createObjectURL(uploadFile))
          }
        } else if (r.data.status === 'failed') {
          setMessage(`Job failed: ${r.data.error_message || 'Unknown error'}`)
        } else {
          schedulePoll()
        }
      } catch (err: any) {
        setMessage(`Poll error: ${err?.message || 'connection issue'} — retrying…`)
        schedulePoll()
      }
    }

    schedulePoll()
    return () => { if (pollTimerRef.current) clearTimeout(pollTimerRef.current) }
  }, [accessToken, job?.id, jobIsTerminal])

  const handleSequenceSubmit = async () => {
    if (!sequence.trim()) { setMessage('Sequence input is required.'); return }
    const payload = { input_type: 'sequence', email: email || undefined, sequence: sequence.trim(), sequence_id: sequenceId || undefined, run_alphafold: runAlphafold }
    setLastPayload(payload)
    setSubmitting(true); setResult(null); setStructureImgUrl(null); setQueryPdbUrl(null); setElapsedSecs(0)
    try {
      const r = await axios.post<HostedJob>(`${API_BASE_URL}/jobs`, payload)
      setJob(r.data)
      setAccessToken(r.data.access_token || '')
      setMessage(`Job ${r.data.id} queued — worker will pick it up automatically.`)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Failed to create job.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUploadSubmit = async () => {
    if (!uploadFile) { setMessage('Choose a file before submitting.'); return }
    setSubmitting(true); setResult(null); setStructureImgUrl(null); setQueryPdbUrl(null); setElapsedSecs(0)
    const form = new FormData()
    form.append('input_type', uploadType)
    if (email) form.append('email', email)
    form.append('file', uploadFile)
    try {
      const r = await axios.post<HostedJob>(`${API_BASE_URL}/jobs/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setJob(r.data)
      setAccessToken(r.data.access_token || '')
      setMessage(`Job ${r.data.id} queued — worker will pick it up automatically.`)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Failed to create job.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRetry = async () => {
    if (!lastPayload) return
    setResult(null); setStructureImgUrl(null); setElapsedSecs(0); setMessage('')
    setSubmitting(true)
    try {
      const r = await axios.post<HostedJob>(`${API_BASE_URL}/jobs`, lastPayload)
      setJob(r.data)
      setAccessToken(r.data.access_token || '')
      setMessage(`Retry job ${r.data.id} queued.`)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Retry failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const downloadAlphafoldPdb = async () => {
    if (!job || !accessToken) return
    setDownloading(true)
    try {
      const r = await axios.get(`${API_BASE_URL}/jobs/files/${job.id}/alphafold`, {
        headers: { 'x-job-token': accessToken },
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = `${job.id}.alphafold.pdb`
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Download failed.')
    } finally {
      setDownloading(false)
    }
  }

  const downloadDbPdb = async (structureId: string) => {
    if (!job || !accessToken) return
    try {
      const r = await axios.get(`${API_BASE_URL}/jobs/files/${job.id}/pdb/${structureId}`, {
        headers: { 'x-job-token': accessToken },
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = `${structureId}.pdb`
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Download failed.')
    }
  }

  const handlePrintPdf = () => window.print()

  // Derived metrics from result
  const firstResult  = result?.processing_result?.results?.[0]
  const tmScore      = firstResult?.tm_align_result?.tm_score ?? (result?.summary?.tm_score as number | undefined)
  const eValue       = firstResult?.blast_result?.e_value
  const identity     = firstResult?.blast_result?.identity
  const bestMatch    = firstResult?.best_match_id ?? (result?.summary?.best_match_id as string | undefined)
  const classification = firstResult?.classification ?? (result?.summary?.classification as string | undefined)
  const alphaStatus  = result?.alphafold?.status
  const topMatches   = firstResult?.tm_align_result?.top_matches ?? []

  if (!mounted) return <div style={{ minHeight: '100vh', background: '#0a0e1a' }} />

  return (
    <div className={styles.container}>

      {/* Nav */}
      <nav className={styles.nav}>
        <div className={styles.navLogo}>
          <div className={styles.navLogoIcon}>E</div>
          <span className={styles.navTitle}>EffectorDB · Analysis Console</span>
        </div>
        {modeInfo && (
          <span className={styles.navBadge}>
            {String(modeInfo.mode)} mode
          </span>
        )}
      </nav>

      <div className={styles.shell}>

        {/* Hero */}
        <div className={styles.hero}>
          <h1>Protein Effector <span>Analysis</span></h1>
          <p className={styles.heroSub}>
            Async pipeline — sequence search (BLAST), structure comparison (TM-align), and optional
            AlphaFold prediction via {modeInfo ? String(modeInfo.mode).toUpperCase() : 'HPC'}.
            Jobs are queued and processed by the worker; results are returned when ready.
          </p>
          {modeInfo && (
            <p className={styles.modeNote}>
              <strong>{String(modeInfo.mode)}</strong> — {String(modeInfo.message)}
            </p>
          )}
        </div>

        {/* Input panel */}
        <div className={styles.inputPanel}>
          <div className={styles.panelHeader}>
            <div className={styles.panelHeaderDot} />
            <span className={styles.panelTitle}>Submit Job</span>
          </div>
          <div className={styles.panelBody}>

            {/* Shared email */}
            <div className={styles.field}>
              <label className={styles.label}>Email (optional)</label>
              <input className={styles.input} value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>

            {/* Tabs */}
            <div className={styles.tabs}>
              <button className={`${styles.tab} ${activeTab === 'sequence' ? styles.tabActive : ''}`} onClick={() => setActiveTab('sequence')}>
                Paste Sequence
              </button>
              <button className={`${styles.tab} ${activeTab === 'upload' ? styles.tabActive : ''}`} onClick={() => setActiveTab('upload')}>
                Upload File (PDB / FASTA)
              </button>
            </div>

            {activeTab === 'sequence' && (
              <>
                <div className={styles.fieldRow}>
                  <div className={styles.field} style={{ marginBottom: 0 }}>
                    <label className={styles.label}>Sequence ID (optional)</label>
                    <input className={styles.input} value={sequenceId} onChange={e => setSequenceId(e.target.value)} placeholder="EFF_001" />
                  </div>
                </div>
                <div className={styles.field} style={{ marginTop: 16 }}>
                  <label className={styles.label}>Protein Sequence</label>
                  <textarea
                    className={styles.textarea}
                    value={sequence}
                    onChange={e => setSequence(e.target.value)}
                    placeholder="MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPK..."
                    rows={6}
                  />
                </div>
                <label className={styles.checkRow}>
                  <input type="checkbox" checked={runAlphafold} onChange={e => setRunAlphafold(e.target.checked)} />
                  Run AlphaFold structure prediction if no match found (requires HPC GPU node)
                </label>
                <div className={styles.btnRow}>
                  <button className={styles.submitBtn} disabled={submitting} onClick={handleSequenceSubmit}>
                    {submitting ? 'Submitting…' : '▶ Run Analysis'}
                  </button>
                </div>
              </>
            )}

            {activeTab === 'upload' && (
              <>
                <div className={styles.field}>
                  <label className={styles.label}>Upload Type</label>
                  <select className={styles.select} value={uploadType} onChange={e => setUploadType(e.target.value as 'structure' | 'fasta')}>
                    <option value="structure">Structure (PDB / CIF)</option>
                    <option value="fasta">Batch FASTA</option>
                  </select>
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>File</label>
                  <input
                    className={styles.input}
                    type="file"
                    accept={uploadType === 'structure' ? '.pdb,.cif' : '.fasta,.fa,.fas'}
                    onChange={e => setUploadFile(e.target.files?.[0] || null)}
                  />
                </div>
                <div className={styles.btnRow}>
                  <button className={styles.submitBtn} disabled={submitting} onClick={handleUploadSubmit}>
                    {submitting ? 'Uploading…' : '▶ Submit Upload'}
                  </button>
                </div>
              </>
            )}

          </div>
        </div>

        {/* Status terminal */}
        {(job || message) && (
          <div className={styles.terminal}>
            <div className={styles.terminalBar}>
              <div className={styles.termDot} style={{ background: '#ff5f57' }} />
              <div className={styles.termDot} style={{ background: '#febc2e' }} />
              <div className={styles.termDot} style={{ background: '#28c840' }} />
              <span className={styles.terminalTitle}>job monitor</span>
              {job && (
                <span className={`${styles.statusBadge} ${statusClass(job.status)}`}>
                  <span
                    className={`${styles.statusDot} ${job.status === 'running' ? styles.pulseDot : ''}`}
                    style={{ background: statusDotColor(job.status) }}
                  />
                  {job.status}
                </span>
              )}
            </div>
            <div className={styles.terminalBody}>
              {message && <div className={styles.termMsg}>{'> '}{message}</div>}
              {job && !jobIsTerminal && elapsedSecs > 0 && (
                <div className={styles.termRow}>
                  <span className={styles.termKey}>elapsed</span>
                  <span className={styles.termVal}>{Math.floor(elapsedSecs / 60)}:{String(elapsedSecs % 60).padStart(2, '0')}</span>
                </div>
              )}
              {job && (
                <>
                  <div className={styles.termRow}><span className={styles.termKey}>job_id</span><span className={styles.termVal}>{job.id}</span></div>
                  <div className={styles.termRow}><span className={styles.termKey}>backend_mode</span><span className={styles.termVal}>{job.backend_mode}</span></div>
                  {job.remote_job_id && <div className={styles.termRow}><span className={styles.termKey}>slurm_job_id</span><span className={styles.termVal}>{job.remote_job_id}</span></div>}
                  <div className={styles.termRow}><span className={styles.termKey}>created_at</span><span className={styles.termVal}>{job.created_at}</span></div>
                  {job.started_at  && <div className={styles.termRow}><span className={styles.termKey}>started_at</span><span className={styles.termVal}>{job.started_at}</span></div>}
                  {job.completed_at && <div className={styles.termRow}><span className={styles.termKey}>completed_at</span><span className={styles.termVal}>{job.completed_at}</span></div>}
                  {job.error_message && <div className={styles.termRow}><span className={styles.termKey}>error</span><span className={styles.termVal} style={{ color: '#ff6666' }}>{job.error_message}</span></div>}
                  {job.status === 'failed' && lastPayload?.input_type === 'sequence' && (
                    <div style={{ marginTop: 12 }}>
                      <button className={styles.secondaryBtn} onClick={handleRetry} disabled={submitting}>
                        ↻ Retry
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className={styles.resultsPanel}>
            <div className={styles.panelHeader}>
              <div className={styles.panelHeaderDot} style={{ background: '#00c864', boxShadow: '0 0 6px #00c864' }} />
              <span className={styles.panelTitle} style={{ color: '#00c864' }}>Analysis Results</span>
            </div>

            {/* Metrics row */}
            <div className={styles.metricsRow}>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>Classification</span>
                {classification
                  ? <span className={`${styles.classificationBadge} ${classificationStyle(classification)}`}>{classification}</span>
                  : <span className={styles.metricValue}>—</span>
                }
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>TM-Score</span>
                <span className={`${styles.metricValue} ${tmScoreColor(tmScore)}`}>{fmt(tmScore)}</span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>BLAST E-value</span>
                <span className={styles.metricValue} style={{ color: '#7a9abf' }}>{fmtEval(eValue)}</span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>Sequence Identity</span>
                <span className={styles.metricValue} style={{ color: '#7a9abf' }}>
                  {identity != null ? `${(identity * 100).toFixed(1)}%` : '—'}
                </span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>Best Match</span>
                <span className={styles.metricValue} style={{ fontSize: '0.78rem', color: '#b8d4e8', wordBreak: 'break-all' }}>{bestMatch ?? '—'}</span>
              </div>
              <div className={styles.metric} style={{ flexBasis: '100%' }}>
                <span className={styles.metricLabel}>RMSD</span>
                <span className={styles.metricValue} style={{ color: '#b8d4e8' }}>{firstResult?.tm_align_result?.rmsd != null ? firstResult.tm_align_result.rmsd.toFixed(2) + ' Å' : '—'}</span>
              </div>
              {alphaStatus && (
                <div className={styles.metric}>
                  <span className={styles.metricLabel}>AlphaFold</span>
                  <span className={`${styles.metricValue} ${alphaStatus === 'completed' ? styles.metricGreen : alphaStatus === 'failed' ? styles.metricRed : styles.metricCyan}`}>
                    {alphaStatus}
                  </span>
                </div>
              )}
            </div>

            {/* Top-10 TM-align matches table */}
            {topMatches.length > 0 && (
              <div className={styles.batchTable} id="tm-matches-table">
                <div className={styles.batchHeader}>
                  <span className={styles.panelTitle}>Top TM-align Matches</span>
                </div>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Structure ID</th>
                      <th>TM-Score</th>
                      <th>RMSD (Å)</th>
                      <th>Aligned Length</th>
                      <th>Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topMatches.map((m, i) => (
                      <tr key={i}>
                        <td style={{ color: '#8899aa', fontSize: '0.8rem' }}>{i + 1}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#b8d4e8' }}>{m.structure}</td>
                        <td style={{ color: m.tm_score >= 0.5 ? '#00c864' : m.tm_score >= 0.3 ? '#f0a000' : '#ff4444' }}>{m.tm_score.toFixed(3)}</td>
                        <td style={{ color: '#b8d4e8' }}>{m.rmsd.toFixed(2)}</td>
                        <td style={{ color: '#8899aa' }}>{m.aligned_length}</td>
                        <td>
                          <button
                            className={styles.secondaryBtn}
                            style={{ padding: '3px 10px', fontSize: '0.75rem' }}
                            onClick={() => downloadDbPdb(m.structure)}
                          >
                            ↓ PDB
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* FASTA batch: all results table */}
            {(result?.processing_result?.results?.length ?? 0) > 1 && (
              <div className={styles.batchTable}>
                <div className={styles.batchHeader}>
                  <span className={styles.panelTitle}>All Sequences ({result!.processing_result!.results!.length})</span>
                </div>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Query ID</th>
                      <th>Best Match</th>
                      <th>TM-score</th>
                      <th>E-value</th>
                      <th>Classification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result!.processing_result!.results!.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{r.query_id ?? '—'}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: '#b8d4e8' }}>{r.best_match_id ?? '—'}</td>
                        <td style={{ color: (r.tm_align_result?.tm_score ?? 0) >= 0.5 ? '#00c864' : (r.tm_align_result?.tm_score ?? 0) >= 0.3 ? '#f0a000' : '#ff4444' }}>
                          {r.tm_align_result?.tm_score != null ? r.tm_align_result.tm_score.toFixed(3) : '—'}
                        </td>
                        <td style={{ color: '#7a9abf', fontSize: '0.8rem' }}>
                          {r.blast_result?.e_value != null ? r.blast_result.e_value.toExponential(2) : '—'}
                        </td>
                        <td>
                          <span className={`${styles.classificationBadge} ${classificationStyle(r.classification)}`}>
                            {r.classification ?? '—'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Structure image */}
            {structureImgUrl && (
              <div className={styles.vizPanel}>
                <div className={styles.vizHeader}>
                  <div className={styles.panelHeaderDot} />
                  <span className={styles.vizTitle}>Structure Preview</span>
                </div>
                <p className={styles.vizCaption}>
                  Best-match structure rendered by PyMOL — rainbow cartoon, ray-traced 800×600
                </p>
                <img src={structureImgUrl} alt="Structure preview" className={styles.vizImage} />
              </div>
            )}

            {/* 3D superimposed structure viewer */}
            {queryPdbUrl && bestMatch && job && (
              <div className={styles.vizPanel} id="structure-viewer">
                <div className={styles.vizHeader}>
                  <div className={styles.panelHeaderDot} />
                  <span className={styles.vizTitle}>Superimposed Structure View</span>
                </div>
                <p className={styles.vizCaption}>
                  Query (blue) superimposed with best DB match (orange) — interactive 3D viewer
                </p>
                <StructureViewer
                  queryPdbUrl={queryPdbUrl}
                  matchPdbUrl={`${API_BASE_URL}/jobs/files/${job.id}/pdb/${bestMatch}`}
                  matchId={bestMatch}
                  accessToken={accessToken}
                />
              </div>
            )}

            {/* Action buttons */}
            <div className={styles.rawSection}>
              <div className={styles.btnRow} style={{ marginBottom: 16 }}>
                {result?.alphafold?.pdb_local_path && (
                  <button className={styles.secondaryBtn} disabled={downloading} onClick={downloadAlphafoldPdb}>
                    {downloading ? 'Downloading…' : '↓ Download AlphaFold PDB'}
                  </button>
                )}
                <button className={styles.secondaryBtn} onClick={handlePrintPdf}>
                  ↓ Download PDF Report
                </button>
              </div>

              {/* Raw JSON toggle */}
              <button className={styles.rawToggle} onClick={() => setRawOpen(o => !o)}>
                <span className={styles.rawToggleIcon}>{rawOpen ? '−' : '+'}</span>
                Raw Result Payload
              </button>
              {rawOpen && (
                <pre className={styles.pre}>{JSON.stringify(result, null, 2)}</pre>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
