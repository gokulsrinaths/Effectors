# Processing Time Estimates

## Structure Upload (PDB/CIF)

**What happens:**
- Uploads your structure file
- Compares it against ALL 470 structures in the database using TM-align
- Returns top matches sorted by TM-score

**Processing Time:**
- **First upload (no cache):** 8-15 minutes
  - Each TM-align comparison: ~1-2 seconds
  - 470 comparisons × 1-2 seconds = ~8-15 minutes
  - Timeout per comparison: 30 seconds (safety limit)
  
- **Subsequent uploads (cached):** < 1 second
  - Results are cached based on file hash
  - If you upload the same file again, results are instant

**Optimization:**
- Results are cached, so repeated uploads are fast
- The system processes comparisons sequentially (one at a time)
- Failed comparisons are skipped and don't stop the process

## Sequence Upload (Single Sequence)

**What happens:**
1. BLAST search against sequence database (~1-5 seconds)
2. If hit found → Map to structure → TM-align against all structures (8-15 minutes)
3. If no hit → Return "novel sequence" status (~1-5 seconds)

**Processing Time:**
- **BLAST search only (no structure match):** 1-5 seconds
- **BLAST + TM-align (structure found):** 8-15 minutes
  - BLAST: 1-5 seconds
  - TM-align: 8-15 minutes (same as structure upload)

**Timeout Settings:**
- BLAST search: 60 seconds timeout
- TM-align per comparison: 30 seconds timeout

## FASTA Upload (Multiple Sequences)

**What happens:**
- Processes each sequence independently
- Each sequence follows the same logic as single sequence upload

**Processing Time:**
- **Per sequence:** Same as single sequence (1-5 seconds or 8-15 minutes)
- **Total time:** Number of sequences × time per sequence
- Example: 10 sequences with BLAST hits = 10 × (8-15 minutes) = 80-150 minutes

**Note:** Sequences are processed sequentially, not in parallel.

## Performance Tips

1. **Use caching:** Upload the same structure file multiple times - second time is instant
2. **Structure uploads are faster** if you already have the PDB file (skips BLAST step)
3. **First-time processing is slower** - subsequent requests benefit from cache
4. **Large structures** may take longer per comparison (up to 30 seconds each)

## Current Database Size

- **Structure database:** 470 PDB files
- **Sequence database:** Indexed FASTA file (effector_sequences.fasta)

## Real-World Estimates

Based on typical protein structures (100-500 residues):

| Operation | First Time | Cached |
|-----------|------------|--------|
| Structure Upload | 8-15 min | < 1 sec |
| Sequence (BLAST only) | 1-5 sec | N/A |
| Sequence (BLAST + TM-align) | 8-15 min | < 1 sec* |

*Cached if same structure file is compared again

