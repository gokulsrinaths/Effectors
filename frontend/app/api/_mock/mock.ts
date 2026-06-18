import type { BlastResult, ClassificationResult, ProcessingResult, TmAlignResult } from './types'

function nowIso() {
  return new Date().toISOString()
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n))
}

// Tiny deterministic hash for stable demo outputs.
function hashString(input: string) {
  let h = 2166136261
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  // unsigned
  return h >>> 0
}

function pick<T>(arr: T[], seed: number) {
  return arr[seed % arr.length]
}

function pseudo(seed: number) {
  // xorshift32
  let x = seed || 1
  x ^= x << 13
  x ^= x >>> 17
  x ^= x << 5
  return (x >>> 0) / 0xffffffff
}

function makeTm(seed: number): TmAlignResult {
  const r1 = pseudo(seed)
  const r2 = pseudo(seed ^ 0x9e3779b9)
  const tm = clamp(0.35 + r1 * 0.55, 0.2, 0.95)
  const rmsd = clamp(1.2 + r2 * 6.5, 0.8, 9.9)
  const aln = Math.floor(120 + r1 * 260)
  const targets = [
    'AvrE_family_001',
    'HopM1_like_017',
    'T3SS_effector_042',
    'XopQ_like_009',
    'Putative_effector_103',
  ]
  return {
    target_id: pick(targets, seed),
    tm_score: Number(tm.toFixed(3)),
    rmsd: Number(rmsd.toFixed(2)),
    alignment_length: aln,
  }
}

function makeBlast(sequence: string, seed: number): BlastResult {
  const r1 = pseudo(seed ^ 0xa5a5a5a5)
  const r2 = pseudo(seed ^ 0x5a5a5a5a)
  const hitIds = [
    'PSCE1038d',
    'PSCE1117d',
    'PSCE119d',
    'PSCE1114d',
    'PSCE1043d',
  ]
  const e = Math.pow(10, -Math.floor(20 + r1 * 80))
  const identity = clamp(0.28 + r2 * 0.68, 0.1, 0.98)
  const cov = clamp(0.35 + pseudo(seed ^ 0x1234567) * 0.6, 0.1, 1.0)
  const aln = Math.floor(80 + cov * 420)
  return {
    hit_id: pick(hitIds, seed),
    e_value: e,
    identity: Number(identity.toFixed(3)),
    query_coverage: Number(cov.toFixed(3)),
    alignment_length: aln,
  }
}

function makeVisualization(id: string) {
  return {
    image: `/api/mock/visualization/${encodeURIComponent(id)}`,
    cached: true,
  }
}

export function mockStructureResult(filename: string): ProcessingResult {
  const seed = hashString(filename)
  const tm = makeTm(seed)
  const classification =
    tm.tm_score >= 0.5 ? 'Known structural family' : 'Novel structure'

  const queryId = filename.replace(/\.(pdb|cif)$/i, '')
  const bestMatchId = tm.target_id
  const result: ClassificationResult = {
    query_id: queryId,
    classification,
    tm_score: tm.tm_score,
    best_match_id: bestMatchId,
    tm_align_result: tm,
    visualization: makeVisualization(bestMatchId),
  }

  return {
    job_id: `struct_demo_${(seed % 1_000_000).toString().padStart(6, '0')}`,
    status: 'completed',
    results: [result],
    completed_at: nowIso(),
    alphafold_queued: false,
  }
}

export function mockSequenceResult(sequence: string, sequenceId?: string): ProcessingResult {
  const norm = sequence.trim().toUpperCase().replace(/[^A-Z]/g, '')
  const seed = hashString(sequenceId ? `${sequenceId}:${norm}` : norm)
  const blast = makeBlast(norm, seed)
  const tm = makeTm(seed ^ 0xdeadbeef)

  const isNovel = norm.length < 80 || blast.identity < 0.3
  const classification = isNovel
    ? 'Novel sequence - structure prediction required'
    : tm.tm_score >= 0.5
      ? 'Known structural family'
      : 'Structurally similar'

  const queryId = sequenceId?.trim() || `seq_${(seed % 1_000_000).toString().padStart(6, '0')}`
  const bestMatchId = isNovel ? undefined : tm.target_id

  const result: ClassificationResult = {
    query_id: queryId,
    classification,
    tm_score: isNovel ? undefined : tm.tm_score,
    best_match_id: bestMatchId,
    blast_result: blast,
    tm_align_result: isNovel ? undefined : tm,
    visualization: bestMatchId ? makeVisualization(bestMatchId) : undefined,
  }

  return {
    job_id: `seq_demo_${(seed % 1_000_000).toString().padStart(6, '0')}`,
    status: 'completed',
    results: [result],
    completed_at: nowIso(),
    alphafold_queued: isNovel,
  }
}

export function mockFastaResult(fastaText: string): ProcessingResult {
  const lines = fastaText.split(/\r?\n/)
  const entries: Array<{ id: string; seq: string }> = []
  let currentId: string | null = null
  let currentSeq: string[] = []

  const flush = () => {
    if (currentId && currentSeq.length) {
      entries.push({ id: currentId, seq: currentSeq.join('') })
    }
  }

  for (const raw of lines) {
    const line = raw.trim()
    if (!line) continue
    if (line.startsWith('>')) {
      flush()
      currentId = (line.slice(1).split(/\s+/)[0] || `seq_${entries.length + 1}`).trim()
      currentSeq = []
    } else {
      currentSeq.push(line)
    }
  }
  flush()

  const seed = hashString(entries.map(e => e.id).join('|') || fastaText.slice(0, 128))

  const results: ClassificationResult[] = entries.slice(0, 25).map((e, idx) => {
    const perSeed = hashString(`${e.id}:${e.seq}`) ^ (idx * 2654435761)
    const blast = makeBlast(e.seq, perSeed)
    const tm = makeTm(perSeed ^ 0x1337c0de)
    const norm = e.seq.trim().toUpperCase().replace(/[^A-Z]/g, '')
    const isNovel = norm.length < 80 || blast.identity < 0.3
    const classification = isNovel
      ? 'Novel sequence - structure prediction required'
      : tm.tm_score >= 0.5
        ? 'Known structural family'
        : 'Structurally similar'
    const bestMatchId = isNovel ? undefined : tm.target_id
    return {
      query_id: e.id,
      classification,
      tm_score: isNovel ? undefined : tm.tm_score,
      best_match_id: bestMatchId,
      blast_result: blast,
      tm_align_result: isNovel ? undefined : tm,
      visualization: bestMatchId ? makeVisualization(bestMatchId) : undefined,
    }
  })

  return {
    job_id: `fasta_demo_${(seed % 1_000_000).toString().padStart(6, '0')}`,
    status: 'completed',
    results,
    completed_at: nowIso(),
    alphafold_queued: results.some(r => r.classification.includes('prediction required')),
  }
}

