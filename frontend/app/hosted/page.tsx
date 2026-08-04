'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import styles from './page.module.css'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://effectors-production.up.railway.app'

type JobStatus = 'queued' | 'reserved' | 'submitted' | 'running' | 'completed' | 'failed'

interface HostedJob {
  id: string
  input_type: string
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
  tm_score_chain1?: number
  tm_score_chain2?: number
  tm_score_best?: number
  alignment_type?: string
  coverage_query?: number
  coverage_target?: number
  rmsd: number
  aligned_length: number
}

interface TmAlign {
  tm_score?: number
  tm_score_chain1?: number
  tm_score_chain2?: number
  tm_score_best?: number
  alignment_type?: string
  coverage_query?: number
  coverage_target?: number
  seq_id?: number
  rmsd?: number
  top_matches?: TmMatch[]
}

interface HostedResult {
  processing_result?: {
    results?: Array<{
      query_id?: string
      blast_result?: { e_value?: number; identity?: number; hit_id?: string }
      tm_align_result?: TmAlign
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
  const s = c.toLowerCase()
  if (s.includes('known') || s.includes('already')) return styles.classKnown
  // Checked before 'similar' so "Partial / domain match" does not fall through
  // to the "novel" style, which would be the opposite of what it means.
  if (s.includes('partial') || s.includes('domain')) return styles.classDomain
  if (s.includes('similar')) return styles.classSimilar
  return styles.classNovel
}

// Bands per Zhang & Skolnick 2005: below 0.20 is indistinguishable from randomly
// chosen unrelated proteins; 0.50 and above implies the same SCOP/CATH fold.
const TM_SAME_FOLD_MIN = 0.5
const TM_UNRELATED_MAX = 0.2

function tmScoreColor(score?: number) {
  if (score == null) return ''
  if (score >= TM_SAME_FOLD_MIN) return styles.metricGreen
  if (score >= TM_UNRELATED_MAX) return styles.metricYellow
  return styles.metricRed
}

const ALIGNMENT_TYPE_TEXT: Record<string, string> = {
  full_fold: 'Same fold',
  domain_match: 'Domain match',
  ambiguous: 'Ambiguous',
  unrelated: 'Unrelated',
}

function fmtPct(v?: number): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(0)}%`
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

function TmScoreValue({ value, other }: { value?: number; other?: number }) {
  const isHigher = value != null && other != null && value > other
  return (
    <span className={`${styles.scoreValue} ${tmScoreColor(value)} ${isHigher ? styles.scoreHigher : ''}`}>
      {value != null ? value.toFixed(3) : '—'}
      {isHigher && <span className={styles.higherBadge}>Higher</span>}
    </span>
  )
}

function AlignmentTypeBadge({ type }: { type?: string }) {
  if (!type) return <span className={styles.metricValue}>—</span>
  return (
    <span className={`${styles.alignBadge} ${styles[`align_${type}`] || ''}`}>
      {ALIGNMENT_TYPE_TEXT[type] || type}
    </span>
  )
}

function ScoreLegend() {
  return (
    <div className={styles.legend}>
      <p className={styles.legendLead}>
        TM-align reports <strong>two</strong> scores because structural similarity is
        directional. <strong>Chain 1</strong> is normalized by the length of your query;
        <strong> Chain 2</strong> by the length of the database structure. A high Chain 2
        with a low Chain 1 means your query <em>contains</em> that structure as a domain
        rather than matching it as a whole — a real hit that a single score would hide.
      </p>
      <ul className={styles.legendBands}>
        <li><span className={styles.metricGreen}>■</span> <strong>≥ 0.50</strong> — same fold (SCOP/CATH)</li>
        <li><span className={styles.metricYellow}>■</span> <strong>0.20 – 0.50</strong> — ambiguous</li>
        <li><span className={styles.metricRed}>■</span> <strong>&lt; 0.20</strong> — unrelated, at the level of randomly chosen proteins</li>
      </ul>
      <p className={styles.legendCite}>Thresholds per Zhang &amp; Skolnick, <em>Nucleic Acids Research</em> 33:2302–2309 (2005).</p>
    </div>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function HostedPage() {
  const [mounted, setMounted]         = useState(false)
  const [activeTab, setActiveTab]     = useState<'sequence' | 'upload'>('sequence')
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
  const [downloadingReport, setDownloadingReport] = useState(false)
  const [structureImgUrl, setStructureImgUrl] = useState<string | null>(null)
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
    const payload = { input_type: 'sequence', sequence: sequence.trim(), sequence_id: sequenceId || undefined, run_alphafold: runAlphafold }
    setLastPayload(payload)
    setSubmitting(true); setResult(null); setStructureImgUrl(null); setElapsedSecs(0)
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
    setSubmitting(true); setResult(null); setStructureImgUrl(null); setElapsedSecs(0)
    const form = new FormData()
    form.append('input_type', uploadType)
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

  const downloadReportPdf = async () => {
    if (!job || !accessToken) return
    setDownloadingReport(true)
    try {
      const r = await axios.get(`${API_BASE_URL}/jobs/files/${job.id}/report-pdf`, {
        headers: { 'x-job-token': accessToken },
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(r.data)
      const a = document.createElement('a')
      a.href = url; a.download = `effector-report-${job.id}.pdf`
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || err?.message || 'Report download failed.')
    } finally {
      setDownloadingReport(false)
    }
  }

  const handlePrintPdf = () => {
    // The dark page background is applied as an inline style on <body>, which a
    // stylesheet cannot reach from inside a CSS module. Swap it for the print
    // and put it back afterwards.
    const prev = document.body.style.backgroundColor
    document.body.style.backgroundColor = '#ffffff'
    const restore = () => {
      document.body.style.backgroundColor = prev
      window.removeEventListener('afterprint', restore)
    }
    window.addEventListener('afterprint', restore)
    window.print()
  }

  // Derived metrics from result
  const firstResult  = result?.processing_result?.results?.[0]
  const tmAlign      = firstResult?.tm_align_result
  const summary      = result?.summary as Record<string, unknown> | undefined
  const tmScore      = tmAlign?.tm_score ?? (summary?.tm_score as number | undefined)
  const tmScoreChain1 = tmAlign?.tm_score_chain1 ?? (summary?.tm_score_chain1 as number | undefined) ?? tmScore
  // Falls back to the summary so the target score still shows when only the
  // condensed summary is available.
  const tmScoreChain2 = tmAlign?.tm_score_chain2 ?? (summary?.tm_score_chain2 as number | undefined)
  const alignmentType = tmAlign?.alignment_type ?? (summary?.alignment_type as string | undefined)
  const coverageQuery = tmAlign?.coverage_query ?? (summary?.coverage_query as number | undefined)
  const coverageTarget = tmAlign?.coverage_target ?? (summary?.coverage_target as number | undefined)
  const seqIdentity   = tmAlign?.seq_id ?? (summary?.seq_id as number | undefined)
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

            {/* Email field intentionally hidden: Railway blocks outbound SMTP
                (Errno 101, no route to port 587), so a delivery promise here
                would be false. The backend plumbing — the email column, request
                schema, PDF generation and send path — is all still in place;
                restore this block once an HTTP-API mail provider is configured. */}

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

            <ScoreLegend />

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
                <span className={styles.metricLabel}>Alignment</span>
                <AlignmentTypeBadge type={alignmentType} />
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>TM-Score Query (Chain 1)</span>
                <span className={styles.metricValue}>
                  <TmScoreValue value={tmScoreChain1} other={tmScoreChain2} />
                </span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>TM-Score Target (Chain 2)</span>
                <span className={styles.metricValue}>
                  <TmScoreValue value={tmScoreChain2} other={tmScoreChain1} />
                </span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>Coverage (query / target)</span>
                <span className={styles.metricValue} style={{ color: '#b8d4e8' }}>
                  {fmtPct(coverageQuery)} / {fmtPct(coverageTarget)}
                </span>
              </div>
              <div className={styles.metric}>
                <span className={styles.metricLabel}>Structural Seq. Identity</span>
                <span className={styles.metricValue} style={{ color: '#7a9abf' }}>{fmtPct(seqIdentity)}</span>
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
                  <span className={styles.batchNote}>Ranked by the better of the two normalized scores</span>
                </div>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Structure ID</th>
                      <th>Query TM-Score (Chain 1)</th>
                      <th>Target TM-Score (Chain 2)</th>
                      <th>Alignment</th>
                      <th>Aligned Length</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topMatches.map((m, i) => (
                      <tr key={i}>
                        <td style={{ color: '#8899aa', fontSize: '0.8rem' }}>{i + 1}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: '#b8d4e8' }}>{m.structure}</td>
                        <td><TmScoreValue value={m.tm_score_chain1 ?? m.tm_score} other={m.tm_score_chain2} /></td>
                        <td><TmScoreValue value={m.tm_score_chain2} other={m.tm_score_chain1 ?? m.tm_score} /></td>
                        <td><AlignmentTypeBadge type={m.alignment_type} /></td>
                        <td style={{ color: '#8899aa' }}>{m.aligned_length}</td>
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
                      <th>Query TM-score (Chain 1)</th>
                      <th>Target TM-score (Chain 2)</th>
                      <th>E-value</th>
                      <th>Classification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result!.processing_result!.results!.map((r, i) => (
                      <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{r.query_id ?? '—'}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: '#b8d4e8' }}>{r.best_match_id ?? '—'}</td>
                        <td><TmScoreValue value={r.tm_align_result?.tm_score_chain1 ?? r.tm_align_result?.tm_score} other={r.tm_align_result?.tm_score_chain2} /></td>
                        <td><TmScoreValue value={r.tm_align_result?.tm_score_chain2} other={r.tm_align_result?.tm_score_chain1 ?? r.tm_align_result?.tm_score} /></td>
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


            {/* Action buttons */}
            <div className={styles.rawSection}>
              <div className={styles.btnRow} style={{ marginBottom: 16 }}>
                {result?.alphafold?.pdb_local_path && (
                  <button className={styles.secondaryBtn} disabled={downloading} onClick={downloadAlphafoldPdb}>
                    {downloading ? 'Downloading…' : '↓ Download AlphaFold PDB'}
                  </button>
                )}
                <button className={styles.secondaryBtn} disabled={downloadingReport} onClick={downloadReportPdf}>
                  {downloadingReport ? 'Preparing…' : '↓ Download PDF Report'}
                </button>
                <button className={styles.secondaryBtn} onClick={handlePrintPdf}>
                  ⎙ Print
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
