export interface BlastResult {
  hit_id: string
  e_value: number
  identity: number
  query_coverage?: number
  alignment_length: number
}

export interface TmAlignResult {
  target_id: string
  tm_score: number
  tm_score_chain1?: number
  tm_score_chain2?: number
  tm_score_best?: number
  alignment_type?: string
  coverage_query?: number
  coverage_target?: number
  seq_id?: number
  rmsd: number
  alignment_length: number
}

export interface ClassificationResult {
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

export interface ProcessingResult {
  job_id: string
  status: string
  results: ClassificationResult[]
  completed_at: string
  alphafold_queued?: boolean
}
