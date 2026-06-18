'use client'

import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import styles from './page.module.css'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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

interface HostedResult {
  processing_result?: Record<string, unknown>
  summary?: Record<string, unknown>
}

export default function HostedPage() {
  const [email, setEmail] = useState('')
  const [sequenceId, setSequenceId] = useState('')
  const [sequence, setSequence] = useState('')
  const [uploadType, setUploadType] = useState<'structure' | 'fasta'>('structure')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [job, setJob] = useState<HostedJob | null>(null)
  const [result, setResult] = useState<HostedResult | null>(null)
  const [accessToken, setAccessToken] = useState('')
  const [message, setMessage] = useState('Create a hosted job, then let the worker process it.')
  const [submitting, setSubmitting] = useState(false)
  const [modeInfo, setModeInfo] = useState<Record<string, unknown> | null>(null)
  const [runAlphafold, setRunAlphafold] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const jobIsTerminal = useMemo(() => {
    return job?.status === 'completed' || job?.status === 'failed'
  }, [job])

  useEffect(() => {
    axios.get(`${API_BASE_URL}/jobs/mode`).then((response) => {
      setModeInfo(response.data)
    }).catch(() => {
      setModeInfo(null)
    })
  }, [])

  useEffect(() => {
    if (!job || jobIsTerminal) {
      return
    }

    const interval = window.setInterval(async () => {
      try {
        const response = await axios.get<HostedJob>(`${API_BASE_URL}${job.poll_path}`, {
          headers: accessToken ? { 'x-job-token': accessToken } : undefined,
        })
        setJob(response.data)
        if (response.data.status === 'completed' && response.data.result_path) {
          const resultResponse = await axios.get<HostedResult>(`${API_BASE_URL}${response.data.result_path}`, {
            headers: accessToken ? { 'x-job-token': accessToken } : undefined,
          })
          setResult(resultResponse.data)
          setMessage('Job completed. Review the condensed result and raw payload below.')
        } else if (response.data.status === 'failed') {
          setMessage(`Job failed: ${response.data.error_message || 'Unknown error'}`)
        }
      } catch (error: any) {
        setMessage(error?.message || 'Failed to poll job status.')
      }
    }, 3000)

    return () => window.clearInterval(interval)
  }, [accessToken, job, jobIsTerminal])

  const handleSequenceSubmit = async () => {
    if (!sequence.trim()) {
      setMessage('Sequence input is required.')
      return
    }

    setSubmitting(true)
    setResult(null)
    try {
      const response = await axios.post<HostedJob>(`${API_BASE_URL}/jobs`, {
        input_type: 'sequence',
        email: email || undefined,
        sequence: sequence.trim(),
        sequence_id: sequenceId || undefined,
        run_alphafold: runAlphafold,
      })
      setJob(response.data)
      setAccessToken(response.data.access_token || '')
      setMessage(`Created sequence job ${response.data.id}. The worker will pick it up automatically.`)
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'Failed to create sequence job.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUploadSubmit = async () => {
    if (!uploadFile) {
      setMessage('Choose a file before submitting.')
      return
    }

    setSubmitting(true)
    setResult(null)
    const formData = new FormData()
    formData.append('input_type', uploadType)
    if (email) {
      formData.append('email', email)
    }
    formData.append('file', uploadFile)

    try {
      const response = await axios.post<HostedJob>(`${API_BASE_URL}/jobs/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setJob(response.data)
      setAccessToken(response.data.access_token || '')
      setMessage(`Created ${uploadType} job ${response.data.id}. The worker will pick it up automatically.`)
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'Failed to create upload job.')
    } finally {
      setSubmitting(false)
    }
  }

  const downloadAlphafoldPdb = async () => {
    if (!job) return
    if (!accessToken) {
      setMessage('Missing job access token. Re-create the job and retry.')
      return
    }

    setDownloading(true)
    try {
      const response = await axios.get(`${API_BASE_URL}/jobs/files/${job.id}/alphafold`, {
        headers: { 'x-job-token': accessToken },
        responseType: 'blob',
      })
      const blobUrl = window.URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = `${job.id}.alphafold.pdb`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(blobUrl)
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'Failed to download AlphaFold PDB.')
    } finally {
      setDownloading(false)
    }
  }


  return (
    <div className={styles.container}>
      <div className={styles.shell}>
        <section className={styles.hero}>
          <h1>Hosted Effector Workflow</h1>
          <p>
            This page uses the async hosted API instead of the synchronous demo flow.
            Jobs are created first, then processed by the worker. Use this as the
            starting point for a public-facing deployment.
          </p>
          {modeInfo && (
            <p className={styles.note}>
              Execution mode: <strong>{String(modeInfo.mode)}</strong>. {String(modeInfo.message)}
            </p>
          )}
        </section>

        <div className={styles.grid}>
          <section className={styles.card}>
            <h2>Sequence Job</h2>
            <p>Create a hosted job from a single protein sequence.</p>
            <div className={styles.field}>
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div className={styles.field}>
              <label>Sequence ID</label>
              <input value={sequenceId} onChange={(e) => setSequenceId(e.target.value)} placeholder="EFF_001" />
            </div>
            <div className={styles.field}>
              <label>Sequence</label>
              <textarea
                value={sequence}
                onChange={(e) => setSequence(e.target.value)}
                placeholder="Paste protein sequence or FASTA-formatted single sequence"
              />
            </div>
            <div className={styles.field}>
              <label>
                <input
                  type="checkbox"
                  checked={runAlphafold}
                  onChange={(e) => setRunAlphafold(e.target.checked)}
                />{' '}
                Run AlphaFold (HPC)
              </label>
            </div>
            <div className={styles.buttonRow}>
              <button className={styles.button} disabled={submitting} onClick={handleSequenceSubmit}>
                Create Sequence Job
              </button>
            </div>
          </section>

          <section className={styles.card}>
            <h2>Upload Job</h2>
            <p>Stage a structure or FASTA file through the hosted API.</p>
            <div className={styles.field}>
              <label>Email</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div className={styles.field}>
              <label>Upload Type</label>
              <select value={uploadType} onChange={(e) => setUploadType(e.target.value as 'structure' | 'fasta')}>
                <option value="structure">structure</option>
                <option value="fasta">fasta</option>
              </select>
            </div>
            <div className={styles.field}>
              <label>File</label>
              <input
                type="file"
                accept={uploadType === 'structure' ? '.pdb,.cif' : '.fasta,.fa,.fas'}
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className={styles.buttonRow}>
              <button className={styles.button} disabled={submitting} onClick={handleUploadSubmit}>
                Create Upload Job
              </button>
            </div>
          </section>
        </div>

        <section className={styles.statusBox}>
          <h2>Job Status</h2>
          <div className={styles.statusLine}>message={message}</div>
          {job && (
            <>
              <div className={styles.statusLine}>job_id={job.id}</div>
              <div className={styles.statusLine}>status={job.status as JobStatus}</div>
              <div className={styles.statusLine}>backend_mode={job.backend_mode}</div>
              {job.remote_job_id && <div className={styles.statusLine}>remote_job_id={job.remote_job_id}</div>}
              <div className={styles.statusLine}>created_at={job.created_at}</div>
              {job.started_at && <div className={styles.statusLine}>started_at={job.started_at}</div>}
              {job.completed_at && <div className={styles.statusLine}>completed_at={job.completed_at}</div>}
            </>
          )}
        </section>

        {(job?.summary || result) && (
          <section className={styles.summary}>
            <h2>Result Summary</h2>
            {job?.summary && (
              <pre>{JSON.stringify(job.summary, null, 2)}</pre>
            )}
            {job?.status === 'completed' && (
              <div className={styles.buttonRow}>
                <button className={styles.button} disabled={downloading} onClick={downloadAlphafoldPdb}>
                  {downloading ? 'Downloading…' : 'Download AlphaFold PDB'}
                </button>
              </div>
            )}
            {result && (
              <>
                <h3>Raw Result Payload</h3>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
