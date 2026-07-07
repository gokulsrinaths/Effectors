'use client'

import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import styles from './page.module.css'

const HOSTED_API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Toast {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
}

type StepStatus = 'pending' | 'active' | 'done'

interface BlastResult {
  hit_id: string
  e_value: number
  identity: number
  query_coverage?: number
  alignment_length: number
}

interface TmAlignResult {
  target_id: string
  tm_score: number
  rmsd: number
  alignment_length: number
}

interface ClassificationResult {
  query_id: string
  classification: string
  tm_score?: number
  best_match_id?: string
  blast_result?: BlastResult
  tm_align_result?: TmAlignResult
  visualization?: { image?: string; cached?: boolean }
}

interface JobResponse {
  id: string
  status: string
  access_token?: string
  poll_path: string
  result_path?: string
  error_message?: string
  backend_mode?: string
}

interface JobResult {
  processing_result?: {
    results: ClassificationResult[]
    alphafold_queued?: boolean
    job_id?: string
  }
  summary?: Record<string, unknown>
}

// ─── Step labels per input type ──────────────────────────────────────────────

const STEP_LABELS: Record<string, string[]> = {
  structure: [
    'Uploading structure file',
    'Running TM-align against database',
    'Gathering results',
    'Complete',
  ],
  sequence: [
    'Parsing sequence',
    'Running BLAST + TM-align',
    'Gathering results',
    'Complete',
  ],
  fasta: [
    'Uploading FASTA file',
    'Running BLAST + TM-align per sequence',
    'Gathering results',
    'Complete',
  ],
}

// Maps job status → which step index is active (0-based)
function statusToStepIndex(status: string): number {
  if (status === 'queued') return 0
  if (status === 'reserved' || status === 'running' || status === 'submitted') return 1
  if (status === 'completed') return 2
  return 0
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function Home() {
  const [mounted, setMounted] = useState(false)
  const [activeTab, setActiveTab] = useState<'structure' | 'sequence' | 'fasta'>('sequence')
  const [sequenceInput, setSequenceInput] = useState('')
  const [sequenceId, setSequenceId] = useState('')
  const [runAlphafold, setRunAlphafold] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [results, setResults] = useState<ClassificationResult[]>([])
  const [noResults, setNoResults] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [processingSteps, setProcessingSteps] = useState<{ label: string; status: StepStatus }[]>([])
  const [jobInfo, setJobInfo] = useState<{ id: string; token: string } | null>(null)
  const [elapsedSecs, setElapsedSecs] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef<number>(0)
  const pollFailuresRef = useRef(0)

  // Clean up polling on unmount
  useEffect(() => {
    setMounted(true)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const addToast = (type: Toast['type'], title: string, message: string) => {
    const id = Date.now().toString()
    setToasts(prev => [...prev, { id, type, title, message }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 6000)
  }

  const removeToast = (id: string) => setToasts(prev => prev.filter(t => t.id !== id))

  function initSteps(inputType: string) {
    const labels = STEP_LABELS[inputType] || STEP_LABELS.sequence
    setProcessingSteps(labels.map((label, i) => ({
      label,
      status: i === 0 ? 'active' : 'pending',
    })))
  }

  function advanceStep(idx: number) {
    setProcessingSteps(prev =>
      prev.map((s, i) => ({
        ...s,
        status: i < idx ? 'done' : i === idx ? 'active' : 'pending',
      }))
    )
  }

  function completeSteps() {
    setProcessingSteps(prev => prev.map(s => ({ ...s, status: 'done' })))
  }

  function startPolling(jobId: string, token: string, inputType: string) {
    if (pollRef.current) clearInterval(pollRef.current)
    startTimeRef.current = Date.now()
    pollFailuresRef.current = 0
    setElapsedSecs(0)

    pollRef.current = setInterval(async () => {
      setElapsedSecs(Math.floor((Date.now() - startTimeRef.current) / 1000))
      try {
        const { data: job } = await axios.get<JobResponse>(
          `${HOSTED_API}/jobs/${jobId}`,
          { headers: { 'x-job-token': token } }
        )
        pollFailuresRef.current = 0

        advanceStep(statusToStepIndex(job.status))

        if (job.status === 'completed') {
          clearInterval(pollRef.current!)
          completeSteps()
          try {
            const { data: resultData } = await axios.get<JobResult>(
              `${HOSTED_API}/jobs/results/${jobId}`,
              { headers: { 'x-job-token': token } }
            )
            const resultsList = resultData.processing_result?.results ?? []
            if (resultsList.length === 0) {
              setNoResults(true)
            } else {
              setNoResults(false)
              setResults(resultsList)
              const alphafoldQ = resultData.processing_result?.alphafold_queued
              if (alphafoldQ) {
                addToast('info', 'AlphaFold Queued', 'Novel sequence(s) queued for structure prediction.')
              }
              addToast('success', 'Processing Complete', `${resultsList.length} result(s) ready.`)
            }
          } catch {
            addToast('error', 'Result Fetch Failed', 'Job completed but results could not be retrieved.')
          }
          setProcessing(false)

        } else if (job.status === 'failed') {
          clearInterval(pollRef.current!)
          setProcessing(false)
          setProcessingSteps([])
          addToast('error', 'Job Failed', job.error_message || 'Unknown error during processing.')
        }
      } catch {
        pollFailuresRef.current += 1
        if (pollFailuresRef.current >= 3) {
          clearInterval(pollRef.current!)
          setProcessing(false)
          addToast('error', 'Connection Lost', 'Lost contact with server after 3 attempts. Refresh the page to check job status.')
        }
      }
    }, 2000)
  }

  // ── Submit handlers ──────────────────────────────────────────────────────

  async function handleSequenceSubmit() {
    if (!sequenceInput.trim()) {
      addToast('error', 'Missing Input', 'Please enter a protein sequence.')
      return
    }
    setProcessing(true)
    setResults([])
    setNoResults(false)
    setJobInfo(null)
    initSteps('sequence')

    try {
      const { data: job } = await axios.post<JobResponse>(`${HOSTED_API}/jobs`, {
        input_type: 'sequence',
        sequence: sequenceInput.trim(),
        sequence_id: sequenceId.trim() || undefined,
        run_alphafold: runAlphafold,
      })
      setJobInfo({ id: job.id, token: job.access_token || '' })
      advanceStep(0)
      startPolling(job.id, job.access_token || '', 'sequence')
    } catch (err: unknown) {
      setProcessing(false)
      setProcessingSteps([])
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      addToast('error', 'Submission Failed', detail || 'Could not create sequence job.')
    }
  }

  async function handleFileUpload(file: File, inputType: 'structure' | 'fasta') {
    setProcessing(true)
    setResults([])
    setNoResults(false)
    setJobInfo(null)
    initSteps(inputType)

    const form = new FormData()
    form.append('input_type', inputType)
    form.append('file', file)
    try {
      const { data: job } = await axios.post<JobResponse>(`${HOSTED_API}/jobs/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setJobInfo({ id: job.id, token: job.access_token || '' })
      advanceStep(0)
      startPolling(job.id, job.access_token || '', inputType)
    } catch (err: unknown) {
      setProcessing(false)
      setProcessingSteps([])
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      addToast('error', 'Upload Failed', detail || `Could not create ${inputType} job.`)
    }
  }

  function handleStructureChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.match(/\.(pdb|cif)$/i)) {
      addToast('error', 'Invalid File', 'Please upload a .pdb or .cif file.')
      return
    }
    handleFileUpload(file, 'structure')
  }

  function handleFastaChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.match(/\.(fasta|fa|fas)$/i)) {
      addToast('error', 'Invalid File', 'Please upload a .fasta, .fa, or .fas file.')
      return
    }
    handleFileUpload(file, 'fasta')
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (!mounted) return null

  return (
    <div className={styles.container}>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            <div className="toast-header">{t.title}</div>
            <div className="toast-message">{t.message}</div>
            <button
              onClick={() => removeToast(t.id)}
              style={{ position: 'absolute', top: 8, right: 8, background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#6c757d' }}
            >×</button>
          </div>
        ))}
      </div>

      {/* Header */}
      <header className={styles.header}>
        <h1>Structure-based Effector Discovery Platform</h1>
        <p className={styles.subtitle}>
          Identify and classify protein effectors through sequence search (BLAST) and
          structure comparison (TM-align). Submit a structure, sequence, or batch FASTA
          file — results are processed by the pipeline and returned when ready.
        </p>
      </header>

      <main className={styles.main}>

        {/* Input panel */}
        <section className={styles.inputPanel}>
          <h2>Submit Input</h2>


          {/* Tabs */}
          <div className={styles.tabs}>
            {(['sequence', 'structure', 'fasta'] as const).map(tab => (
              <button
                key={tab}
                className={`${styles.tab} ${activeTab === tab ? styles.activeTab : ''}`}
                onClick={() => { if (!processing) setActiveTab(tab) }}
                disabled={processing}
              >
                {tab === 'sequence' && 'Paste Sequence'}
                {tab === 'structure' && 'Upload Structure (PDB/CIF)'}
                {tab === 'fasta' && 'Upload FASTA File'}
              </button>
            ))}
          </div>

          <div className={styles.tabContent}>

            {/* Sequence tab */}
            {activeTab === 'sequence' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Paste a single protein sequence. BLAST searches the effector database;
                  if a hit is found, TM-align compares the matched structure against the
                  full database.
                </p>
                <div className={styles.sequenceInputGroup}>
                  <label className={styles.label}>
                    Sequence ID (optional):
                    <input
                      type="text"
                      value={sequenceId}
                      onChange={e => setSequenceId(e.target.value)}
                      placeholder="e.g., EFF_001"
                      className={styles.textInput}
                      disabled={processing}
                    />
                  </label>
                  <label className={styles.label}>
                    Protein Sequence:
                    <textarea
                      value={sequenceInput}
                      onChange={e => setSequenceInput(e.target.value)}
                      placeholder=">sequence_id&#10;MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAP..."
                      rows={7}
                      className={styles.textarea}
                      disabled={processing}
                    />
                  </label>
                  <label className={styles.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, fontWeight: 400 }}>
                    <input
                      type="checkbox"
                      checked={runAlphafold}
                      onChange={e => setRunAlphafold(e.target.checked)}
                      disabled={processing}
                    />
                    Run AlphaFold structure prediction if no match found (requires HPC)
                  </label>
                  <button
                    onClick={handleSequenceSubmit}
                    disabled={processing || !sequenceInput.trim()}
                    className={styles.submitButton}
                  >
                    {processing ? 'Processing…' : 'Run Analysis'}
                  </button>
                </div>
              </div>
            )}

            {/* Structure tab */}
            {activeTab === 'structure' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Upload a PDB or CIF structure file. TM-align will compare it against
                  all 470 structures in the effector database and return the top matches.
                </p>
                <label className={styles.fileLabel}>
                  <input
                    type="file"
                    accept=".pdb,.cif"
                    onChange={handleStructureChange}
                    disabled={processing}
                    className={styles.fileInput}
                  />
                  <span className={styles.fileButton}>
                    {processing ? 'Processing…' : 'Choose Structure File'}
                  </span>
                </label>
              </div>
            )}

            {/* FASTA tab */}
            {activeTab === 'fasta' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Upload a FASTA file with one or more protein sequences. Each sequence
                  is processed independently through BLAST and TM-align.
                </p>
                <label className={styles.fileLabel}>
                  <input
                    type="file"
                    accept=".fasta,.fa,.fas"
                    onChange={handleFastaChange}
                    disabled={processing}
                    className={styles.fileInput}
                  />
                  <span className={styles.fileButton}>
                    {processing ? 'Processing…' : 'Choose FASTA File'}
                  </span>
                </label>
              </div>
            )}

          </div>
        </section>

        {/* Processing status */}
        {processing && processingSteps.length > 0 && (
          <section className={styles.statusPanel}>
            <h2>Processing</h2>
            <div className={styles.stepsContainer}>
              {processingSteps.map((step, idx) => (
                <div
                  key={idx}
                  className={`${styles.stepRow} ${
                    step.status === 'active' ? styles.active
                    : step.status === 'done' ? styles.done
                    : styles.pending
                  }`}
                >
                  <div className={styles.stepIcon}>
                    {step.status === 'done' ? (
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <circle cx="10" cy="10" r="9" stroke="#28a745" strokeWidth="2"/>
                        <path d="M6 10l3 3 5-5" stroke="#28a745" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : step.status === 'active' ? (
                      <div className={styles.stepSpinner} />
                    ) : (
                      <div className={styles.stepDot} />
                    )}
                  </div>
                  <span className={styles.stepLabel}>{step.label}</span>
                </div>
              ))}
            </div>
            {jobInfo && (
              <p style={{ marginTop: 14, fontSize: '0.8rem', color: '#6c757d', fontFamily: 'monospace' }}>
                job_id: {jobInfo.id} &nbsp;·&nbsp; elapsed: {Math.floor(elapsedSecs / 60)}:{String(elapsedSecs % 60).padStart(2, '0')}
              </p>
            )}
          </section>
        )}

        {/* Empty results state */}
        {noResults && (
          <section className={styles.statusPanel}>
            <h2>No Classification Found</h2>
            <p style={{ color: '#6c757d', fontSize: '0.9rem', marginTop: 8 }}>
              The job completed but returned no results. This can happen if:
            </p>
            <ul style={{ color: '#6c757d', fontSize: '0.9rem', marginTop: 8, paddingLeft: 20 }}>
              <li>The sequence had no BLAST hit in the effector database</li>
              <li>The uploaded structure could not be parsed by TM-align</li>
              <li>The FASTA file contained no valid sequences</li>
            </ul>
          </section>
        )}

        {/* Results */}
        {results.length > 0 && (
          <section className={styles.resultsPanel}>
            <h2>Results</h2>
            {jobInfo && (
              <p style={{ fontSize: '0.8rem', color: '#6c757d', marginBottom: 16, fontFamily: 'monospace' }}>
                job_id: {jobInfo.id}
              </p>
            )}
            <div className={styles.resultsTable}>
              <table>
                <thead>
                  <tr>
                    <th>Query ID</th>
                    <th>Best Match</th>
                    <th>TM-score</th>
                    <th>Classification</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <ResultRow key={i} result={r} apiBase={HOSTED_API} jobId={jobInfo?.id} jobToken={jobInfo?.token} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

      </main>

      <footer className={styles.footer}>
        <p>Structure-based Effector Discovery Pipeline</p>
      </footer>

    </div>
  )
}

// ─── Result row ───────────────────────────────────────────────────────────────

function ResultRow({
  result,
  apiBase,
  jobId,
  jobToken,
}: {
  result: ClassificationResult
  apiBase: string
  jobId?: string
  jobToken?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const [structureImgUrl, setStructureImgUrl] = useState<string | null>(null)
  const [imgLoaded, setImgLoaded] = useState(false)

  useEffect(() => {
    if (!expanded || !jobId || !jobToken) return
    if (structureImgUrl) return
    const url = `${apiBase}/jobs/files/${jobId}/structure-image`
    fetch(url, { headers: { 'x-job-token': jobToken } })
      .then(res => {
        if (!res.ok) return
        res.blob().then(blob => setStructureImgUrl(URL.createObjectURL(blob)))
      })
      .catch(() => {})
  }, [expanded, jobId, jobToken, apiBase, structureImgUrl])

  const classColor = (c: string) => {
    if (c.includes('Already in database')) return '#28a745'
    if (c.includes('Known structural family') || c.includes('Structurally similar')) return '#e6a817'
    if (c.includes('Novel') || c.includes('missing') || c.includes('required')) return '#dc3545'
    return '#6c757d'
  }

  return (
    <>
      <tr>
        <td>{result.query_id}</td>
        <td>{result.best_match_id || '—'}</td>
        <td>{result.tm_score != null ? result.tm_score.toFixed(3) : '—'}</td>
        <td>
          <span style={{ color: classColor(result.classification), fontWeight: 600 }}>
            {result.classification}
          </span>
        </td>
        <td>
          <button onClick={() => setExpanded(x => !x)} className={styles.expandButton}>
            {expanded ? '−' : '+'}
          </button>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={5} className={styles.detailsCell}>
            <div className={styles.detailsContent}>

              {result.blast_result && (
                <div>
                  <h4>BLAST</h4>
                  <ul>
                    <li>Hit ID: {result.blast_result.hit_id}</li>
                    <li>E-value: {result.blast_result.e_value.toExponential(2)}</li>
                    <li>Identity: {(result.blast_result.identity * 100).toFixed(1)}%</li>
                    {result.blast_result.query_coverage != null && (
                      <li>Query Coverage: {(result.blast_result.query_coverage * 100).toFixed(1)}%</li>
                    )}
                    <li>Alignment Length: {result.blast_result.alignment_length}</li>
                  </ul>
                </div>
              )}

              {result.tm_align_result && (
                <div>
                  <h4>TM-align</h4>
                  <ul>
                    <li>Target: {result.tm_align_result.target_id}</li>
                    <li>TM-score: {result.tm_align_result.tm_score.toFixed(3)}</li>
                    <li>RMSD: {result.tm_align_result.rmsd.toFixed(2)} Å</li>
                    <li>Alignment Length: {result.tm_align_result.alignment_length}</li>
                  </ul>
                </div>
              )}

              {structureImgUrl && (
                <div style={{ marginTop: 16 }}>
                  <p style={{ fontSize: '0.8rem', color: '#6c757d', marginBottom: 6 }}>Structure preview</p>
                  <img
                    src={structureImgUrl}
                    alt="Structure preview"
                    style={{
                      maxWidth: '100%',
                      maxHeight: 360,
                      borderRadius: 6,
                      border: '1px solid #dee2e6',
                      display: imgLoaded ? 'block' : 'none',
                    }}
                    onLoad={() => setImgLoaded(true)}
                  />
                  {!imgLoaded && (
                    <div style={{ fontSize: '0.8rem', color: '#6c757d' }}>Loading preview…</div>
                  )}
                </div>
              )}

              {result.best_match_id && (
                <div style={{ marginTop: 12 }}>
                  <button
                    onClick={() =>
                      window.open(
                        `${apiBase}/api/download/pdb?structure_id=${encodeURIComponent(result.best_match_id!)}`,
                        '_blank'
                      )
                    }
                    style={{
                      padding: '7px 16px',
                      background: '#28a745',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 4,
                      fontSize: 14,
                      fontWeight: 500,
                      cursor: 'pointer',
                    }}
                  >
                    Download PDB
                  </button>
                </div>
              )}

            </div>
          </td>
        </tr>
      )}
    </>
  )
}
