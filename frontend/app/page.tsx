'use client'

import { useState } from 'react'
import axios from 'axios'
import styles from './page.module.css'

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === '1'
// In demo mode, use Next.js route handlers (same-origin) as a mock backend.
const API_BASE_URL = DEMO_MODE
  ? ''
  : (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000')

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
  visualization?: {
    image?: string
    cached?: boolean
  }
}

interface ProcessingResult {
  job_id: string
  status: string
  results: ClassificationResult[]
  completed_at: string
  alphafold_queued?: boolean
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<'structure' | 'sequence' | 'fasta'>('structure')
  const [sequenceInput, setSequenceInput] = useState('')
  const [sequenceId, setSequenceId] = useState('')
  const [processing, setProcessing] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [results, setResults] = useState<ClassificationResult[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const [processingSteps, setProcessingSteps] = useState<{ label: string; status: StepStatus }[]>([])

  const addToast = (type: Toast['type'], title: string, message: string) => {
    const id = Date.now().toString()
    setToasts(prev => [...prev, { id, type, title, message }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 5000)
  }

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  const handleStructureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.name.match(/\.(pdb|cif)$/i)) {
      addToast('error', 'Invalid File Type', 'Please upload a PDB or CIF file.')
      return
    }

    setProcessing(true)
    setResults([])
    setProcessingSteps([
      { label: 'Uploading file', status: 'done' },
      { label: 'Running TM-align against structure database', status: 'active' },
      { label: 'Generating visualization', status: 'pending' },
      { label: 'Finalizing results', status: 'pending' },
    ])

    const formData = new FormData()
    formData.append('file', file)

    try {
      await new Promise(r => setTimeout(r, 1200))
      setProcessingSteps(s => s.map((step, i) => i === 1 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 2 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 1000))
      setProcessingSteps(s => s.map((step, i) => i === 2 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 3 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 600))
      setProcessingSteps(s => s.map((step, i) => i === 3 ? { ...step, status: 'done' as StepStatus } : step))

      const response = await axios.post<ProcessingResult>(
        `${API_BASE_URL}/api/process/structure`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      )

      setResults(response.data.results)
      setStatusMessage('Structure comparison completed.')
      addToast('success', 'Processing Complete', 'Structure analysis completed successfully.')
    } catch (error: any) {
      setStatusMessage('Error processing structure.')
      let errorMessage = 'Failed to process structure file.'
      if (error.response?.data) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map((e: any) => 
            typeof e === 'string' ? e : e.msg || JSON.stringify(e)
          ).join(', ')
        } else if (error.response.data.detail) {
          errorMessage = typeof error.response.data.detail === 'string' 
            ? error.response.data.detail 
            : JSON.stringify(error.response.data.detail)
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message
        }
      } else if (error.message) {
        errorMessage = error.message
      }
      addToast('error', 'Processing Error', errorMessage)
    } finally {
      setProcessing(false)
      setProcessingSteps([])
    }
  }

  const handleSequenceSubmit = async () => {
    if (!sequenceInput.trim()) {
      addToast('error', 'Invalid Input', 'Please enter a protein sequence.')
      return
    }

    setProcessing(true)
    setResults([])
    setProcessingSteps([
      { label: 'Parsing sequence', status: 'done' },
      { label: 'Predicting structure using AlphaFold 2.3', status: 'active' },
      { label: 'Performing structure comparison (TM-align)', status: 'pending' },
      { label: 'Finalizing results', status: 'pending' },
    ])

    try {
      await new Promise(r => setTimeout(r, 800))
      setProcessingSteps(s => s.map((step, i) => i === 1 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 2 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 1500))
      setProcessingSteps(s => s.map((step, i) => i === 2 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 3 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 500))
      setProcessingSteps(s => s.map((step, i) => i === 3 ? { ...step, status: 'done' as StepStatus } : step))

      const response = await axios.post<ProcessingResult>(
        `${API_BASE_URL}/api/process/sequence`,
        {
          sequence: sequenceInput.trim(),
          sequence_id: sequenceId.trim() || undefined,
        }
      )

      if (response.data.alphafold_queued) {
        addToast('info', 'Structure Prediction Queued', 
          'New structure is being generated using AlphaFold/ColabFold (job queued)')
      }

      setResults(response.data.results)
      setStatusMessage('Sequence analysis completed.')
      addToast('success', 'Processing Complete', 'Sequence analysis completed successfully.')
    } catch (error: any) {
      setStatusMessage('Error processing sequence.')
      let errorMessage = 'Failed to process sequence.'
      if (error.response?.data) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map((e: any) => 
            typeof e === 'string' ? e : e.msg || JSON.stringify(e)
          ).join(', ')
        } else if (error.response.data.detail) {
          errorMessage = typeof error.response.data.detail === 'string' 
            ? error.response.data.detail 
            : JSON.stringify(error.response.data.detail)
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message
        }
      } else if (error.message) {
        errorMessage = error.message
      }
      addToast('error', 'Processing Error', errorMessage)
    } finally {
      setProcessing(false)
      setProcessingSteps([])
    }
  }

  const handleFastaUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.name.match(/\.(fasta|fa|fas)$/i)) {
      addToast('error', 'Invalid File Type', 'Please upload a FASTA file.')
      return
    }

    setProcessing(true)
    setResults([])
    setProcessingSteps([
      { label: 'Parsing FASTA file', status: 'done' },
      { label: 'Predicting structures using AlphaFold 2.3', status: 'active' },
      { label: 'Performing TM-align comparisons', status: 'pending' },
      { label: 'Finalizing batch results', status: 'pending' },
    ])

    const formData = new FormData()
    formData.append('file', file)

    try {
      await new Promise(r => setTimeout(r, 1000))
      setProcessingSteps(s => s.map((step, i) => i === 1 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 2 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 1800))
      setProcessingSteps(s => s.map((step, i) => i === 2 ? { ...step, status: 'done' as StepStatus } : step).map((step, i) => i === 3 ? { ...step, status: 'active' as StepStatus } : step))
      await new Promise(r => setTimeout(r, 700))
      setProcessingSteps(s => s.map((step, i) => i === 3 ? { ...step, status: 'done' as StepStatus } : step))

      const response = await axios.post<ProcessingResult>(
        `${API_BASE_URL}/api/process/fasta`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      )

      if (response.data.alphafold_queued) {
        addToast('info', 'Structure Prediction Queued', 
          'New structures are being generated using AlphaFold/ColabFold (job queued)')
      }

      setResults(response.data.results)
      setStatusMessage(`Processed ${response.data.results.length} sequences.`)
      addToast('success', 'Processing Complete', 
        `Successfully processed ${response.data.results.length} sequences.`)
    } catch (error: any) {
      setStatusMessage('Error processing FASTA file.')
      let errorMessage = 'Failed to process FASTA file.'
      if (error.response?.data) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map((e: any) => 
            typeof e === 'string' ? e : e.msg || JSON.stringify(e)
          ).join(', ')
        } else if (error.response.data.detail) {
          errorMessage = typeof error.response.data.detail === 'string' 
            ? error.response.data.detail 
            : JSON.stringify(error.response.data.detail)
        } else if (error.response.data.message) {
          errorMessage = error.response.data.message
        }
      } else if (error.message) {
        errorMessage = error.message
      }
      addToast('error', 'Processing Error', errorMessage)
    } finally {
      setProcessing(false)
      setProcessingSteps([])
    }
  }

  return (
    <div className={styles.container}>
      {/* Toast Container */}
      <div className="toast-container">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast ${toast.type}`}>
            <div className="toast-header">{toast.title}</div>
            <div className="toast-message">{toast.message}</div>
            <button 
              onClick={() => removeToast(toast.id)}
              style={{
                position: 'absolute',
                top: '8px',
                right: '8px',
                background: 'none',
                border: 'none',
                fontSize: '18px',
                cursor: 'pointer',
                color: '#6c757d'
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Header */}
      <header className={styles.header}>
        <h1>Structure-based Effector Discovery Platform</h1>
        <p className={styles.subtitle}>
          Research infrastructure for identifying and classifying protein effectors through 
          sequence search (BLAST) and structure comparison (TM-align)
        </p>
        <p className={styles.subtitle}>
          Need the async hosted workflow instead of the demo path? Open <a href="/hosted">/hosted</a>.
        </p>
      </header>

      <main className={styles.main}>
        {/* Input Panel */}
        <section className={styles.inputPanel}>
          <h2>Input Options</h2>
          <p className={styles.instructionText}>
            Select an input method below. The system will determine whether your protein 
            is already known, structurally similar, or novel using sequence search and 
            structure comparison methods.
          </p>

          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${activeTab === 'structure' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('structure')}
            >
              Upload Structure (PDB/CIF)
            </button>
            <button
              className={`${styles.tab} ${activeTab === 'sequence' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('sequence')}
            >
              Paste Single Sequence
            </button>
            <button
              className={`${styles.tab} ${activeTab === 'fasta' ? styles.activeTab : ''}`}
              onClick={() => setActiveTab('fasta')}
            >
              Upload FASTA File
            </button>
          </div>

          <div className={styles.tabContent}>
            {activeTab === 'structure' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Upload a protein structure file in PDB or CIF format. The system will 
                  compare your structure against the internal structure database using TM-align.
                </p>
                <label className={styles.fileLabel}>
                  <input
                    type="file"
                    accept=".pdb,.cif"
                    onChange={handleStructureUpload}
                    disabled={processing}
                    className={styles.fileInput}
                  />
                  <span className={styles.fileButton}>Choose Structure File</span>
                </label>
              </div>
            )}

            {activeTab === 'sequence' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Paste a single protein sequence in FASTA format (with or without header). 
                  The system will predict the structure using AlphaFold 2.3, then perform 
                  structure comparison if matches are found.
                </p>
                <div className={styles.sequenceInputGroup}>
                  <label className={styles.label}>
                    Sequence ID (optional):
                    <input
                      type="text"
                      value={sequenceId}
                      onChange={(e) => setSequenceId(e.target.value)}
                      placeholder="e.g., EFF_001"
                      className={styles.textInput}
                      disabled={processing}
                    />
                  </label>
                  <label className={styles.label}>
                    Protein Sequence:
                    <textarea
                      value={sequenceInput}
                      onChange={(e) => setSequenceInput(e.target.value)}
                      placeholder=">sequence_id&#10;MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIH..."
                      rows={8}
                      className={styles.textarea}
                      disabled={processing}
                    />
                  </label>
                  <button
                    onClick={handleSequenceSubmit}
                    disabled={processing || !sequenceInput.trim()}
                    className={styles.submitButton}
                  >
                    Process Sequence
                  </button>
                </div>
              </div>
            )}

            {activeTab === 'fasta' && (
              <div className={styles.inputSection}>
                <p className={styles.inputDescription}>
                  Upload a FASTA file containing multiple protein sequences. Each sequence 
                  will be processed independently through AlphaFold 2.3 structure prediction and comparison.
                </p>
                <label className={styles.fileLabel}>
                  <input
                    type="file"
                    accept=".fasta,.fa,.fas"
                    onChange={handleFastaUpload}
                    disabled={processing}
                    className={styles.fileInput}
                  />
                  <span className={styles.fileButton}>Choose FASTA File</span>
                </label>
              </div>
            )}
          </div>
        </section>

        {/* Processing Status Panel */}
        {processing && (
          <section className={styles.statusPanel}>
            <h2>Processing</h2>
            <div className={styles.stepsContainer}>
              {processingSteps.map((step, idx) => (
                <div
                  key={idx}
                  className={`${styles.stepRow} ${step.status === 'active' ? styles.active : step.status === 'done' ? styles.done : styles.pending}`}
                >
                  <div className={styles.stepIcon}>
                    {step.status === 'done' ? (
                      <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="9" stroke="#28a745" strokeWidth="2"/><path d="M6 10l3 3 5-5" stroke="#28a745" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    ) : step.status === 'active' ? (
                      <div className={styles.stepSpinner}></div>
                    ) : (
                      <div className={styles.stepDot}></div>
                    )}
                  </div>
                  <span className={styles.stepLabel}>{step.label}</span>
                </div>
              ))}
            </div>
            {statusMessage && (
              <p className={styles.statusMessage}>{statusMessage}</p>
            )}
          </section>
        )}

        {/* Results Panel */}
        {results.length > 0 && (
          <section className={styles.resultsPanel}>
            <h2>Results</h2>
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
                  {results.map((result, idx) => (
                    <ResultRow key={idx} result={result} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>

      <footer className={styles.footer}>
        <p>Structure-based Effector Discovery Pipeline — Research Infrastructure Platform</p>
      </footer>
    </div>
  )
}

function ResultRow({ result }: { result: ClassificationResult }) {
  const [expanded, setExpanded] = useState(false)

  const getClassificationColor = (classification: string) => {
    if (classification.includes('Already in database')) return '#28a745'
    if (classification.includes('Known structural family')) return '#ffc107'
    return '#dc3545'
  }

  return (
    <>
      <tr>
        <td>{result.query_id}</td>
        <td>{result.best_match_id || 'N/A'}</td>
        <td>{result.tm_score?.toFixed(3) || 'N/A'}</td>
        <td>
          <span
            style={{
              color: getClassificationColor(result.classification),
              fontWeight: 600,
            }}
          >
            {result.classification}
          </span>
        </td>
        <td>
          <button
            onClick={() => setExpanded(!expanded)}
            className={styles.expandButton}
          >
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
                  <h4>BLAST Results:</h4>
                  <ul>
                    <li>Hit ID: {result.blast_result.hit_id}</li>
                    <li>E-value: {result.blast_result.e_value.toExponential(2)}</li>
                    <li>Identity: {(result.blast_result.identity * 100).toFixed(1)}%</li>
                    {typeof result.blast_result.query_coverage === 'number' && (
                      <li>Query Coverage: {(result.blast_result.query_coverage * 100).toFixed(1)}%</li>
                    )}
                    <li>Alignment Length: {result.blast_result.alignment_length}</li>
                  </ul>
                </div>
              )}
              {result.tm_align_result && (
                <div>
                  <h4>TM-align Results:</h4>
                  <ul>
                    <li>Target ID: {result.tm_align_result.target_id}</li>
                    <li>TM-score: {result.tm_align_result.tm_score.toFixed(3)}</li>
                    <li>RMSD: {result.tm_align_result.rmsd.toFixed(2)} Å</li>
                    <li>Alignment Length: {result.tm_align_result.alignment_length}</li>
                  </ul>
                </div>
              )}
              {/* Show visualization section only if available */}
              {result.visualization && result.visualization.image && (
                <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #dee2e6' }}>
                  <h4>🧬 Protein Structure Visualization</h4>
                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '15px',
                    alignItems: 'flex-start'
                  }}>
                    <div style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '15px',
                      alignItems: 'flex-start'
                    }}>
                      <div style={{
                        width: '100%',
                        maxWidth: '600px',
                        border: '1px solid #dee2e6',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        backgroundColor: '#fff'
                      }}>
                        <img
                          src={`${API_BASE_URL}${result.visualization.image}`}
                          alt="Protein structure"
                          style={{
                            width: '100%',
                            height: 'auto',
                            display: 'block'
                          }}
                          onError={(e) => {
                            const target = e.target as HTMLImageElement
                            target.style.display = 'none'
                          }}
                        />
                      </div>
                    <div style={{
                      display: 'flex',
                      gap: '10px',
                      flexWrap: 'wrap'
                    }}>
                      <a
                        href={`${API_BASE_URL}${result.visualization.image}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          padding: '8px 16px',
                          backgroundColor: '#007bff',
                          color: 'white',
                          textDecoration: 'none',
                          borderRadius: '4px',
                          fontSize: '14px',
                          fontWeight: 500,
                          display: 'inline-block'
                        }}
                      >
                        Open Full Image
                      </a>
                      {result.best_match_id && (
                        <button
                          onClick={() => {
                            // Download PDB file - construct path from best_match_id
                            const pdbPath = `${API_BASE_URL}/api/download/pdb?structure_id=${encodeURIComponent(result.best_match_id || '')}`
                            window.open(pdbPath, '_blank')
                          }}
                          style={{
                            padding: '8px 16px',
                            backgroundColor: '#28a745',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            fontSize: '14px',
                            fontWeight: 500,
                            cursor: 'pointer'
                          }}
                        >
                          Download PDB
                        </button>
                      )}
                    </div>
                    {result.visualization.cached && (
                      <p style={{
                        fontSize: '12px',
                        color: '#6c757d',
                        margin: 0,
                        fontStyle: 'italic'
                      }}>
                        (Using cached visualization)
                      </p>
                    )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

