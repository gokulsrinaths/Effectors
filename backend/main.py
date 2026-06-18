"""
Structure-based Effector Discovery Pipeline - Backend API

NSF Phase 1: Real BLAST+ and TM-align implementation
NSF Phase 2: AlphaFold integration (deferred)

Research-grade API for structure-based effector discovery.
All biological results are real - no mocks.

External tools are resolved via PATH for portability.
This design supports Windows dev and Linux/HPC deployment.
"""

from fastapi import BackgroundTasks, FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple
import subprocess
import tempfile
import os
import json
import uuid
import pathlib
import hashlib
import logging
import re
import shutil
from datetime import datetime
import asyncio
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Effector Discovery Pipeline API",
    description="Research-grade API for structure-based effector discovery - NSF Phase 1",
    version="1.0.0"
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response Models
class StructureMatchResult(BaseModel):
    """Result for structure upload"""
    status: str
    tm_score: Optional[float] = None
    rmsd: Optional[float] = None
    matched_structure: Optional[str] = None
    method_used: str
    alignment_length: Optional[int] = None
    top_matches: Optional[List[dict]] = None


class SequenceResult(BaseModel):
    """Result for sequence upload"""
    query_id: Optional[str] = None
    status: str
    message: Optional[str] = None
    tm_score: Optional[float] = None
    rmsd: Optional[float] = None
    matched_structure: Optional[str] = None
    blast_hit_id: Optional[str] = None
    blast_evalue: Optional[float] = None
    blast_identity: Optional[float] = None
    blast_query_coverage: Optional[float] = None
    method_used: Optional[str] = None
    alignment_length: Optional[int] = None


class MultiSequenceResult(BaseModel):
    """Result for multi-sequence upload"""
    results: List[SequenceResult]
    total_sequences: int
    processed: int


class StatusResponse(BaseModel):
    """Status endpoint response"""
    blast: dict
    tmalign: dict
    wsl: dict
    structure_db: dict


# Database paths
BASE_DIR = pathlib.Path(__file__).parent.parent
STRUCTURE_DB_PATH = BASE_DIR / "Database"
SEQUENCE_DB_PATH = BASE_DIR / "effector_sequences.fasta"
# Use underscore to avoid space issues with makeblastdb
SEQUENCE_DB_INDEX_PATH = BASE_DIR / "effector_sequences"

# Cache for TM-align results: key = (query_hash, target_filename), value = dict with tm_score, rmsd
_tmalign_cache = {}

# Cache for structure files list
_structure_files_cache = None

# In-memory registry for completed jobs returned by the synchronous frontend API.
_job_store = {}
_job_store_lock = threading.Lock()

# Binary paths (detected at startup)
BLASTP_PATH = None
MAKEBLASTDB_PATH = None
TMALIGN_PATH = None
WSL_AVAILABLE = False
WSL_DISTRO = None
TMALIGN_AVAILABLE = False


def windows_to_wsl_path(windows_path: str) -> str:
    """
    Convert Windows path to WSL path.
    Example: C:/Users/sgoku/file.pdb -> /mnt/c/Users/sgoku/file.pdb
    """
    # Normalize Windows path
    normalized = pathlib.Path(windows_path).resolve()
    drive = normalized.drive.replace(':', '').lower()
    path_parts = normalized.parts[1:]  # Skip drive letter
    
    # Convert to WSL path
    wsl_path = f"/mnt/{drive}/" + "/".join(path_parts)
    return wsl_path.replace('\\', '/')


def check_binary(name: str) -> Optional[str]:
    """
    Check if a binary is available in PATH.
    Returns absolute path if found, None otherwise.
    Uses absolute paths for robustness - does not rely on shell PATH implicitly.
    """
    binary_path = shutil.which(name)
    if binary_path:
        # Convert to absolute path for robustness
        abs_path = pathlib.Path(binary_path).resolve()
        logger.info(f"Found {name} at {abs_path}")
        return str(abs_path)
    return None


def check_wsl_available() -> Tuple[bool, Optional[str]]:
    """
    Check if WSL is available and detect distro.
    Returns (available, distro_name).
    """
    try:
        result = subprocess.run(
            ['wsl', '--list', '--verbose'],
            capture_output=True,
            text=False,  # Get bytes first
            timeout=5,
            check=False
        )
        if result.returncode == 0:
            # Handle UTF-16 encoding (Windows PowerShell output)
            try:
                output = result.stdout.decode('utf-16-le')
            except UnicodeDecodeError:
                try:
                    output = result.stdout.decode('utf-8')
                except:
                    output = result.stdout.decode('utf-8', errors='ignore')
            
            # Parse output to find default distro
            # Format: "* Ubuntu-22.04    Running    2"
            lines = output.split('\n')
            for line in lines:
                line_clean = line.replace('\x00', '').strip()  # Remove null bytes
                if '*' in line_clean:
                    # Default distro marked with asterisk
                    parts = line_clean.split()
                    # Find distro name (first part after asterisk)
                    found_asterisk = False
                    for part in parts:
                        if part == '*':
                            found_asterisk = True
                        elif found_asterisk and part.strip():
                            distro = part.strip()
                            if len(distro) > 2 and not distro.startswith('-'):
                                logger.info(f"WSL available with distro: {distro}")
                                return True, distro
            # If no default marked, try first non-header distro
            for line in lines[1:]:  # Skip header
                line_clean = line.replace('\x00', '').strip()
                if line_clean and not line_clean.startswith('NAME') and not line_clean.startswith('---'):
                    parts = line_clean.split()
                    if len(parts) > 0:
                        distro = parts[0].strip()
                        if distro and distro != '*' and len(distro) > 2:
                            logger.info(f"WSL available with distro: {distro}")
                            return True, distro
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Error checking WSL: {e}")
    
    return False, None


def check_tmalign_native() -> Optional[str]:
    """Check whether a native structure-alignment binary is available and executable."""
    for binary_name in ("TMalign", "USalign"):
        binary_path = check_binary(binary_name)
        if not binary_path:
            continue

        try:
            result = subprocess.run(
                [binary_path, '-h'],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            combined_output = f"{result.stdout}\n{result.stderr}"
            if "TM-align" in combined_output or "US-align" in combined_output or "Usage" in combined_output or result.returncode == 0:
                return binary_path
            logger.warning(f"Native structure-alignment probe returned unexpected output from {binary_path}")
        except Exception as e:
            logger.warning(f"Native structure-alignment probe failed for {binary_path}: {e}")
    return None


def check_tmalign_via_wsl() -> bool:
    """
    Check if TMalign is available via WSL.
    Uses exactly: wsl TMalign -h
    Increased timeout to handle slow WSL startup.
    """
    for attempt in range(3):  # Retry up to 3 times
        try:
            timeout_seconds = 30 if attempt > 0 else 20  # Longer timeout on retries
            result = subprocess.run(
                ['wsl', 'TMalign', '-h'],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False
            )
            combined_output = f"{result.stdout}\n{result.stderr}"
            # TMalign typically returns non-zero exit code but shows usage/help text.
            if 'TM-align' in combined_output:
                logger.info("TMalign available via WSL")
                return True
        except subprocess.TimeoutExpired:
            if attempt < 2:
                logger.warning(f"TM-align check timed out (attempt {attempt + 1}/3). Retrying with longer timeout...")
                import time
                time.sleep(3)  # Brief pause before retry
                continue
            else:
                logger.warning("TM-align check timed out after 3 attempts - WSL may be very slow")
                return False
        except FileNotFoundError:
            logger.warning("WSL not found during TM-align check.")
            return False
        except Exception as e:
            logger.warning(f"Error checking TMalign via WSL (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                import time
                time.sleep(2)
                continue
    
    # Final attempt - check if WSL itself is responsive
    try:
        logger.info("Performing final WSL responsiveness check...")
        result = subprocess.run(
            ['wsl', 'echo', 'test'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        if result.returncode == 0:
            logger.warning("WSL is responsive but TM-align check failed - TM-align may not be installed")
        else:
            logger.warning("WSL is not responding properly")
    except Exception as e:
        logger.warning(f"WSL responsiveness check failed: {e}")
    
    return False


def get_structure_database_files():
    """Get list of all PDB files in the structure database."""
    global _structure_files_cache
    if _structure_files_cache is None:
        if STRUCTURE_DB_PATH.exists():
            _structure_files_cache = list(STRUCTURE_DB_PATH.glob("*.pdb"))
        else:
            _structure_files_cache = []
    return _structure_files_cache


def compute_file_hash(file_path: str) -> str:
    """Compute SHA256 hash of file content for caching."""
    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to compute hash for {file_path}: {e}")
        return ""


_AA3_TO_1 = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    # Common ambiguous/modified residues -> X
    "ASX": "B",
    "GLX": "Z",
    "SEC": "U",
    "PYL": "O",
}


def extract_sequence_from_pdb(pdb_path: str, max_len: int = 5000) -> str:
    """
    Best-effort sequence extraction from a PDB/mmCIF file for degraded-mode demos.

    Preference order:
    1) SEQRES records (PDB) if present
    2) ATOM backbone residue changes (PDB) as a fallback

    Returns an uppercase 1-letter sequence (may contain X/B/Z) or "".
    """
    try:
        seqres_tokens: List[str] = []
        atom_residues: List[str] = []
        last_atom_key = None

        with open(pdb_path, "rt", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("SEQRES"):
                    parts = line.split()
                    # SEQRES <serNum> <chainID> <numRes> <resName...>
                    if len(parts) >= 5:
                        seqres_tokens.extend(parts[4:])
                elif line.startswith("ATOM"):
                    # PDB fixed columns: resName 17-20, chainID 21, resSeq 22-26
                    res3 = line[17:20].strip().upper()
                    chain = line[21:22]
                    resseq = line[22:26].strip()
                    key = (chain, resseq)
                    if key != last_atom_key and res3:
                        atom_residues.append(res3)
                        last_atom_key = key

                if len(seqres_tokens) > max_len:
                    break
                if len(atom_residues) > max_len:
                    break

        if seqres_tokens:
            seq = "".join(_AA3_TO_1.get(r.upper(), "X") for r in seqres_tokens)
            return re.sub(r"[^A-Z]", "", seq.upper())

        if atom_residues:
            seq = "".join(_AA3_TO_1.get(r.upper(), "X") for r in atom_residues)
            return re.sub(r"[^A-Z]", "", seq.upper())
    except Exception as e:
        logger.warning(f"Failed to extract sequence from structure {pdb_path}: {e}")
    return ""


def get_blast_version() -> Optional[str]:
    """Get BLAST+ version string."""
    if not BLASTP_PATH:
        return None
    
    try:
        result = subprocess.run(
            [BLASTP_PATH, '-version'],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        # Parse version from output like "blastp: 2.17.0+"
        match = re.search(r'(\d+\.\d+\.\d+\+)', result.stdout)
        if match:
            return match.group(1)
    except Exception as e:
        logger.warning(f"Failed to get BLAST version: {e}")
    
    return None


def ensure_blast_database_indexed() -> bool:
    """
    Ensure BLAST database is indexed.
    If not indexed, create it using makeblastdb.
    Auto-creates database if FASTA file exists but database is missing.
    Returns True if database is ready, False otherwise.
    """
    # Check if database files exist
    db_files = [
        SEQUENCE_DB_INDEX_PATH.with_suffix('.psq'),
        SEQUENCE_DB_INDEX_PATH.with_suffix('.phr'),
        SEQUENCE_DB_INDEX_PATH.with_suffix('.pin'),
    ]
    
    if all(f.exists() for f in db_files):
        logger.info(f"BLAST database already indexed at {SEQUENCE_DB_INDEX_PATH}")
        return True
    
    # Verify FASTA file exists
    if not SEQUENCE_DB_PATH.exists():
        logger.error(f"Sequence database file not found: {SEQUENCE_DB_PATH}")
        logger.error("Please ensure effector_sequences.fasta exists in the project root")
        return False
    
    # Use makeblastdb from PATH or detected path (must be absolute)
    makeblastdb_binary = MAKEBLASTDB_PATH or check_binary('makeblastdb')
    if not makeblastdb_binary:
        logger.error("makeblastdb not available - cannot index database")
        return False
    
    logger.info(f"Indexing BLAST database from {SEQUENCE_DB_PATH}...")
    try:
        in_path = str(SEQUENCE_DB_PATH.resolve())
        out_path = str(SEQUENCE_DB_INDEX_PATH.resolve())
        
        # Ensure output directory exists
        pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        
        result = subprocess.run(
                [
                    makeblastdb_binary,
                    '-in', in_path,
                    '-dbtype', 'prot',
                    '-out', out_path,
                    '-title', 'Effector Sequences'
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )
        
        # Verify database was created
        if all(f.exists() for f in db_files):
            logger.info(f"BLAST database indexed successfully at {SEQUENCE_DB_INDEX_PATH}")
            return True
        else:
            logger.error("Database indexing completed but files are missing")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to index BLAST database: {e.stderr}")
        logger.error(f"Command: {' '.join([makeblastdb_binary, '-in', in_path, '-dbtype', 'prot', '-out', out_path])}")
        return False
    except Exception as e:
        logger.error(f"Error indexing BLAST database: {e}")
        return False


def parse_tmalign_output(output: str) -> Optional[dict]:
    """
    Parse TM-align stdout to extract TM-score, RMSD, and alignment length.
    Returns dict with 'tm_score' (normalized by Chain_1), 'rmsd', and 'aligned_length'.
    """
    lines = output.split('\n')
    tm_score_query = None
    rmsd = None
    aligned_length = None
    
    for line in lines:
        line = line.strip()
        
        # Parse TM-score normalized by Chain_1 (query structure)
        if 'TM-score=' in line and 'Chain_1' in line:
            try:
                parts = line.split('TM-score=')
                if len(parts) > 1:
                    score_part = parts[1].strip()
                    match = re.search(r'(\d+\.?\d*)', score_part)
                    if match:
                        tm_score_query = float(match.group(1))
            except (ValueError, IndexError, AttributeError) as e:
                logger.warning(f"Failed to parse TM-score: {e}")
        
        # Parse RMSD
        if rmsd is None and 'RMSD=' in line:
            try:
                parts = line.split('RMSD=')
                if len(parts) > 1:
                    rmsd_part = parts[1].strip()
                    match = re.search(r'(\d+\.?\d*)', rmsd_part)
                    if match:
                        rmsd = float(match.group(1))
            except (ValueError, IndexError, AttributeError):
                pass
        
        # Parse alignment length (number of aligned residues)
        if 'Aligned length=' in line or 'Number of residues=' in line:
            try:
                match = re.search(r'(\d+)', line)
                if match:
                    aligned_length = int(match.group(1))
            except (ValueError, AttributeError):
                pass
    
    if tm_score_query is None:
        logger.warning("Could not find TM-score normalized by Chain_1 in TM-align output")
        return None
    
    return {
        'tm_score': tm_score_query,
        'rmsd': rmsd if rmsd is not None else 0.0,
        'aligned_length': aligned_length if aligned_length is not None else 0
    }


def run_tmalign_binary(query_pdb: str, target_pdb: str, timeout: int = 30) -> Optional[dict]:
    """
    Execute TM-align to compare two structures.

    Prefers a native Windows/Linux TM-align binary when available and falls back
    to WSL only when that is the only available execution path.
    
    Returns dict with 'tm_score', 'rmsd', and 'aligned_length', or None if execution failed.
    """
    global TMALIGN_PATH
    if not TMALIGN_PATH:
        TMALIGN_PATH = check_tmalign_native()
    
    try:
        if TMALIGN_PATH:
            logger.debug(f"Running native TM-align: {query_pdb} vs {target_pdb}")
            result = subprocess.run(
                [TMALIGN_PATH, query_pdb, target_pdb],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
        else:
            query_wsl = windows_to_wsl_path(query_pdb)
            target_wsl = windows_to_wsl_path(target_pdb)
            logger.debug(f"Running TMalign via WSL: {query_wsl} vs {target_wsl}")
            result = subprocess.run(
                ['wsl', 'TMalign', query_wsl, target_wsl],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
        
        parsed = parse_tmalign_output(result.stdout)
        if parsed is None:
            logger.warning(f"Failed to parse TM-align output")
            return None
        
        return parsed
        
    except subprocess.TimeoutExpired:
        logger.error(f"TM-align timeout (>{timeout}s)")
        raise RuntimeError(f"TM-align timeout after {timeout}s")
    except subprocess.CalledProcessError as e:
        logger.error(
            f"TM-align failed: exit code {e.returncode}, "
            f"stderr: {e.stderr[:500] if e.stderr else 'N/A'}"
        )
        raise RuntimeError(f"TM-align execution failed: {e.stderr[:200] if e.stderr else 'Unknown error'}")
    except FileNotFoundError:
        if TMALIGN_PATH:
            logger.error("Native TM-align binary not found at runtime")
            raise RuntimeError("Native TM-align not available")
        logger.error("WSL not found")
        raise RuntimeError("WSL not available - cannot run TMalign")
    except Exception as e:
        logger.error(f"Unexpected error running TM-align: {e}", exc_info=True)
        raise


def run_blastp_search(sequence: str, sequence_id: str, timeout: int = 60) -> Optional[dict]:
    """
    Run real BLASTP search against effector sequence database.
    
    External tools are resolved via PATH for portability.
    This design supports Windows dev and Linux/HPC deployment.
    
    Returns dict with hit information if found, None otherwise.
    Thresholds: evalue <= 1e-5, query coverage >= 50%
    """
    # Ensure BLASTP_PATH is set
    global BLASTP_PATH
    if not BLASTP_PATH:
        BLASTP_PATH = check_binary('blastp')
    if not BLASTP_PATH:
        raise RuntimeError("blastp not available")
    
    if not SEQUENCE_DB_INDEX_PATH.with_suffix('.psq').exists():
        raise RuntimeError(f"BLAST database not indexed at {SEQUENCE_DB_INDEX_PATH}")
    
    # Create temporary FASTA file for query sequence
    with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as query_file:
        query_file.write(f">{sequence_id}\n{sequence}\n")
        query_path = query_file.name
    
    try:
        # Create temporary output file for BLAST results
        with tempfile.NamedTemporaryFile(mode='w', suffix='.blast', delete=False) as output_file:
            output_path = output_file.name
        
        # Run BLASTP with tabular output (outfmt 6)
        result = subprocess.run(
            [
                BLASTP_PATH,
                '-query', query_path,
                '-db', str(SEQUENCE_DB_INDEX_PATH),
                '-out', output_path,
                '-outfmt', '6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qcovs',
                '-evalue', '1e-5',
                '-max_target_seqs', '1',
                '-num_threads', '1'
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        
        # Parse BLAST output
        best_hit = None
        best_evalue = float('inf')
        
        with open(output_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                fields = line.split('\t')
                if len(fields) < 12:
                    continue
                
                try:
                    hit_id = fields[1]  # sseqid
                    percent_identity = float(fields[2])  # pident
                    alignment_length = int(fields[3])  # length
                    evalue = float(fields[10])  # evalue
                    query_coverage = float(fields[12]) if len(fields) > 12 else 0.0  # qcovs
                    
                    # Apply thresholds
                    if evalue <= 1e-5 and query_coverage >= 50.0:
                        if evalue < best_evalue:
                            best_evalue = evalue
                            best_hit = {
                                'hit_id': hit_id,
                                'percent_identity': percent_identity,
                                'alignment_length': alignment_length,
                                'evalue': evalue,
                                'query_coverage': query_coverage
                            }
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse BLAST output line: {line[:100]}, error: {e}")
                    continue
        
        # Cleanup temp files
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        if best_hit:
            logger.info(f"BLAST hit found: {best_hit['hit_id']} (e-value={best_hit['evalue']:.2e})")
            return best_hit
        else:
            logger.info(f"No BLAST hit found for {sequence_id}")
            return None
        
    except subprocess.TimeoutExpired:
        logger.error(f"BLASTP timeout (>{timeout}s)")
        raise RuntimeError(f"BLASTP timeout after {timeout}s")
    except subprocess.CalledProcessError as e:
        logger.error(f"BLASTP failed: exit code {e.returncode}, stderr: {e.stderr[:300] if e.stderr else 'N/A'}")
        raise RuntimeError(f"BLASTP execution failed: {e.stderr[:200] if e.stderr else 'Unknown error'}")
    except FileNotFoundError:
        logger.error("blastp not found")
        raise RuntimeError("blastp binary not found in PATH")
    except Exception as e:
        logger.error(f"Unexpected error running BLASTP: {e}", exc_info=True)
        raise
    finally:
        if os.path.exists(query_path):
            os.unlink(query_path)


def lookup_structure_by_id(sequence_id: str) -> Optional[str]:
    """
    Look up structure file by sequence ID in the structure database.
    Matching logic: exact filename, prefix match, or cleaned match.
    """
    db_files = get_structure_database_files()
    if not db_files:
        return None
    
    # Try exact match
    exact_match = f"{sequence_id}__ranked_0.pdb"
    for pdb_file in db_files:
        if pdb_file.name == exact_match:
            return str(pdb_file)
    
    # Try prefix match
    for pdb_file in db_files:
        filename_base = pdb_file.stem
        if filename_base.startswith(sequence_id):
            return str(pdb_file)
    
    # Try cleaned match
    sequence_id_clean = sequence_id.replace("_ranked_0", "").replace("__ranked_0", "")
    for pdb_file in db_files:
        pdb_clean = pdb_file.stem.replace("_ranked_0", "").replace("__ranked_0", "")
        if pdb_clean == sequence_id_clean:
            return str(pdb_file)
    
    return None


def interpret_tm_score(tm_score: float) -> str:
    """
    Interpret TM-score according to thresholds:
    <0.3 = unrelated
    0.3-0.5 = possible similarity
    >0.5 = same fold
    """
    if tm_score < 0.3:
        return "unrelated"
    elif tm_score < 0.5:
        return "possible_similarity"
    else:
        return "same_fold"


def normalize_sequence_input(sequence: str, sequence_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Normalize single-sequence input.

    Accepts either raw sequence text or FASTA-formatted input with an optional header.
    Returns a tuple of (clean_sequence, resolved_sequence_id).
    """
    if not sequence or not sequence.strip():
        raise HTTPException(status_code=400, detail="Sequence cannot be empty")

    lines = [line.strip() for line in sequence.strip().splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="Sequence cannot be empty")

    header_id = None
    sequence_lines = lines
    if lines[0].startswith('>'):
        header = lines[0][1:].strip()
        header_id = header.split()[0] if header else None
        sequence_lines = lines[1:]

    cleaned_sequence = ''.join(sequence_lines).replace(' ', '').upper()
    if not cleaned_sequence:
        raise HTTPException(status_code=400, detail="Sequence cannot be empty")

    resolved_sequence_id = (sequence_id or header_id or f"seq_{uuid.uuid4().hex[:8]}").strip()
    return cleaned_sequence, resolved_sequence_id


# NSF Phase 2: AlphaFold integration (deferred)
def generate_structure_with_alphafold(sequence_id: str, sequence: str) -> dict:
    """
    NSF Phase 2: AlphaFold structure generation.
    
    This function is a placeholder for future AlphaFold/ColabFold integration.
    Currently returns a deferred status message.
    
    DO NOT implement actual AlphaFold here - only return status.
    """
    logger.info(f"AlphaFold structure generation deferred for {sequence_id}")
    return {
        "status": "deferred",
        "message": f"Structure generation queued for {sequence_id}. AlphaFold/ColabFold will be integrated in Phase 2.",
        "sequence_id": sequence_id
    }


def is_tmalign_ready() -> bool:
    """Return whether TM-align is usable in the current environment."""
    return TMALIGN_AVAILABLE


def _get_root_payload() -> dict:
    """Build the root endpoint payload."""
    db_files = get_structure_database_files()
    return {
        "name": "Effector Discovery Pipeline API",
        "version": "1.0.0",
        "status": "operational",
        "phase": "NSF Phase 1 - Real BLAST+ and TM-align",
        "structure_database": {
            "path": str(STRUCTURE_DB_PATH),
            "structures_count": len(db_files),
            "available": STRUCTURE_DB_PATH.exists()
        },
        "sequence_database": {
            "path": str(SEQUENCE_DB_PATH),
            "index_path": str(SEQUENCE_DB_INDEX_PATH),
            "available": SEQUENCE_DB_PATH.exists(),
            "indexed": SEQUENCE_DB_INDEX_PATH.with_suffix('.psq').exists()
        },
        "note": "All tools verified at startup. Use /status for detailed availability."
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """
    API root endpoint.
    
    Returns basic API information and database status.
    For detailed tool availability, use /status endpoint.
    """
    return _get_root_payload()


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Health/status endpoint.
    
    Returns availability status of external bioinformatics tools and databases.
    All checks are performed at runtime - no cached values.
    External tools are resolved via PATH for portability.
    """
    # Check BLAST availability and version
    blast_version = get_blast_version()
    db_indexed = SEQUENCE_DB_INDEX_PATH.with_suffix('.psq').exists()
    
    # Check TM-align availability at runtime.
    native_tmalign = check_tmalign_native()
    wsl_available, wsl_distro = check_wsl_available()
    tmalign_available = bool(native_tmalign) or check_tmalign_via_wsl()
    
    # Check structure database
    structure_files = get_structure_database_files()
    structure_count = len(structure_files)
    
    return StatusResponse(
        blast={
            "available": BLASTP_PATH is not None,
            "version": blast_version or "unknown",
            "indexed": db_indexed
        },
        tmalign={
            "available": tmalign_available,
            "method": "native" if native_tmalign else ("WSL" if tmalign_available and wsl_available else "none")
        },
        wsl={
            "available": wsl_available,
            "distro": wsl_distro or "none"
        },
        structure_db={
            "path": str(STRUCTURE_DB_PATH),
            "available": STRUCTURE_DB_PATH.exists(),
            "count": structure_count
        }
    )


@app.get("/stats")
async def get_stats():
    """Compatibility summary endpoint for older scripts."""
    payload = _get_root_payload()
    payload["tool_status"] = (await get_status()).model_dump()
    payload["jobs_tracked"] = len(_job_store)
    return payload


@app.post("/upload/structure", response_model=StructureMatchResult)
async def upload_structure(file: UploadFile = File(...)):
    """
    CASE A: Structure Upload
    
    Process uploaded PDB structure file:
    1. Check if identical filename exists in database
    2. If not, run TM-align against all structures
    3. Return top matches sorted by TM-score
    """
    logger.info(f"Processing structure upload: {file.filename}")
    
    # Validate file type
    if not file.filename.lower().endswith(('.pdb', '.cif')):
        raise HTTPException(status_code=400, detail="File must be PDB or CIF format")

    if not is_tmalign_ready():
        raise HTTPException(
            status_code=503,
            detail="TM-align is unavailable in this environment. Structure comparison is disabled until WSL/TM-align access is restored."
        )
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    try:
        query_filename = os.path.basename(file.filename)
        
        # Check if identical filename exists
        db_files = get_structure_database_files()
        for db_file in db_files:
            if db_file.name == query_filename:
                logger.info(f"Identical filename found: {query_filename}")
                return StructureMatchResult(
                    status="already_in_database",
                    tm_score=1.0,
                    rmsd=0.0,
                    matched_structure=query_filename,
                    method_used="filename_match",
                    alignment_length=0
                )
        
        # Verify structure database is available
        if not db_files:
            raise HTTPException(
                status_code=503,
                detail=f"Structure database is empty. No PDB files found in {STRUCTURE_DB_PATH}"
                )
        
        # Run TM-align against all structures
        logger.info(f"Running TM-align against {len(db_files)} structures")
        query_hash = compute_file_hash(tmp_path)
        
        matches = []
        comparisons_done = 0
        
        for db_file in db_files:
            db_filename = db_file.stem
            
            # Check cache
            cache_key = (query_hash, db_filename)
            if cache_key in _tmalign_cache:
                cached_result = _tmalign_cache[cache_key]
                matches.append({
                    'structure': db_filename,
                    'tm_score': cached_result['tm_score'],
                    'rmsd': cached_result.get('rmsd', 0.0),
                    'aligned_length': cached_result.get('aligned_length', 0),
                    'cached': True
                })
            else:
                # Run TM-align via WSL
                try:
                    result = run_tmalign_binary(tmp_path, str(db_file))
                    comparisons_done += 1
                    
                    if result:
                        tm_score = result['tm_score']
                        _tmalign_cache[cache_key] = result
                        
                        matches.append({
                            'structure': db_filename,
                            'tm_score': tm_score,
                            'rmsd': result.get('rmsd', 0.0),
                            'aligned_length': result.get('aligned_length', 0),
                            'cached': False,
                            'interpretation': interpret_tm_score(tm_score)
                        })
                except RuntimeError as e:
                    logger.error(f"TM-align failed for {db_filename}: {e}")
                    # Continue with other structures rather than failing completely
                    continue
        
        logger.info(f"Completed {comparisons_done} comparisons")
        
        if not matches:
            return StructureMatchResult(
                status="no_matches",
                tm_score=0.0,
                rmsd=0.0,
                matched_structure=None,
                method_used="TM-align",
                alignment_length=0,
                top_matches=[]
            )
        
        # Sort by TM-score (descending) and get top matches
        matches.sort(key=lambda x: x['tm_score'], reverse=True)
        top_matches = matches[:10]  # Top 10 matches
        
        best_match = matches[0]
        
        return StructureMatchResult(
            status="matched",
            tm_score=best_match['tm_score'],
            rmsd=best_match.get('rmsd', 0.0),
            matched_structure=best_match['structure'],
            method_used="TM-align",
            alignment_length=best_match.get('aligned_length', 0),
            top_matches=top_matches
        )
    
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/upload/sequence", response_model=SequenceResult)
async def upload_sequence(sequence: str, sequence_id: Optional[str] = None):
    """
    CASE B: Single Sequence Upload
    
    Process single protein sequence:
    1. Run BLASTP against sequence database
    2. If hit found, map to structure and run TM-align
    3. If no hit or structure missing, return AlphaFold deferred status
    """
    sequence, seq_id = normalize_sequence_input(sequence, sequence_id)
    logger.info(f"Processing sequence: {seq_id}")
    
    # Step 1: Run BLASTP
    try:
        blast_hit = run_blastp_search(sequence, seq_id)
    except RuntimeError as e:
        error_detail = f"BLAST search failed: {str(e)}"
        logger.error(error_detail)
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
    
    if not blast_hit:
        # No BLAST hit - novel sequence
        logger.info(f"No BLAST hit for {seq_id} - novel sequence")
        generate_structure_with_alphafold(seq_id, sequence)
        return SequenceResult(
            query_id=seq_id,
            status="novel_sequence",
            message="Novel effector. AlphaFold structure will be generated.",
            method_used="BLAST+TM-align"
        )
    
    # Step 2: Map hit ID to structure
    hit_id = blast_hit['hit_id']
    structure_path = lookup_structure_by_id(hit_id)
    
    if not structure_path or not os.path.exists(structure_path):
        # BLAST hit but structure missing
        logger.info(f"BLAST hit {hit_id} but structure not found")
        generate_structure_with_alphafold(seq_id, sequence)
        return SequenceResult(
            query_id=seq_id,
            status="structure_missing",
            message="Structure not found. AlphaFold structure will be generated.",
            blast_hit_id=hit_id,
            blast_evalue=blast_hit['evalue'],
            blast_identity=blast_hit['percent_identity'] / 100.0,
            blast_query_coverage=blast_hit['query_coverage'] / 100.0,
            method_used="BLAST+TM-align"
        )

    if not is_tmalign_ready():
        logger.warning("TM-align unavailable; returning BLAST-only result")
        return SequenceResult(
            query_id=seq_id,
            status="structure_found_no_comparison",
            message="BLAST hit found, but TM-align is unavailable in this environment. Structure comparison is disabled until WSL/TM-align access is restored.",
            matched_structure=os.path.basename(structure_path),
            blast_hit_id=hit_id,
            blast_evalue=blast_hit['evalue'],
            blast_identity=blast_hit['percent_identity'] / 100.0,
            blast_query_coverage=blast_hit['query_coverage'] / 100.0,
            method_used="BLAST"
        )
    
    # Step 3: Run TM-align against database structures
    logger.info(f"Running TM-align for structure: {structure_path}")
    
    db_files = get_structure_database_files()
    if not db_files:
        # Structure found but no database to compare against
        return SequenceResult(
            query_id=seq_id,
            status="structure_found_no_comparison",
            message="Structure found but structure database is empty. Cannot perform TM-align comparison.",
            blast_hit_id=hit_id,
            blast_evalue=blast_hit['evalue'],
            blast_identity=blast_hit['percent_identity'] / 100.0,
            blast_query_coverage=blast_hit['query_coverage'] / 100.0,
            method_used="BLAST"
        )

    best_tm_score = 0.0
    best_rmsd = 0.0
    best_match_structure = None
    best_aligned_length = 0
    
    structure_hash = compute_file_hash(structure_path)
    
    for db_file in db_files:
        db_filename = db_file.stem
        
        # Skip self-comparison
        if str(db_file) == structure_path:
            best_tm_score = 1.0
            best_rmsd = 0.0
            best_match_structure = os.path.basename(structure_path)
            continue
        
        # Check cache
        cache_key = (structure_hash, db_filename)
        if cache_key in _tmalign_cache:
            cached_result = _tmalign_cache[cache_key]
            tm_score = cached_result['tm_score']
        else:
            try:
                tm_result = run_tmalign_binary(structure_path, str(db_file))
                if tm_result is None:
                    continue
                tm_score = tm_result['tm_score']
                _tmalign_cache[cache_key] = tm_result
            except RuntimeError as e:
                logger.error(f"TM-align failed for {db_filename}: {e}")
                continue
        
        if tm_score > best_tm_score:
            best_tm_score = tm_score
            best_rmsd = _tmalign_cache.get(cache_key, {}).get('rmsd', 0.0)
            best_match_structure = db_filename
            best_aligned_length = _tmalign_cache.get(cache_key, {}).get('aligned_length', 0)

    return SequenceResult(
        query_id=seq_id,
        status="blast_hit_with_structure",
        tm_score=best_tm_score,
        rmsd=best_rmsd,
        matched_structure=best_match_structure or os.path.basename(structure_path),
        blast_hit_id=hit_id,
        blast_evalue=blast_hit['evalue'],
        blast_identity=blast_hit['percent_identity'] / 100.0,
        blast_query_coverage=blast_hit['query_coverage'] / 100.0,
        method_used="BLAST+TM-align",
        alignment_length=best_aligned_length or blast_hit['alignment_length']
    )


@app.post("/upload/multisequence", response_model=MultiSequenceResult)
async def upload_multisequence(file: UploadFile = File(...)):
    """
    CASE C: Multi-Sequence Upload
    
    Process multi-FASTA file:
    1. Parse FASTA
    2. Process each sequence independently using CASE B logic
    3. Return array of results
    """
    logger.info(f"Processing multi-sequence file: {file.filename}")
    
    content = await file.read()
    fasta_content = content.decode('utf-8')
    
    # Parse FASTA
    sequences = []
    current_id = None
    current_seq = []
    
    for line in fasta_content.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('>'):
            if current_id and current_seq:
                sequences.append({
                    'id': current_id,
                    'sequence': ''.join(current_seq)
                })
            current_id = line[1:].split()[0] if line[1:] else f"seq_{len(sequences)+1}"
            current_seq = []
        else:
            current_seq.append(line)
    
    if current_id and current_seq:
        sequences.append({
            'id': current_id,
            'sequence': ''.join(current_seq)
        })
    
    if not sequences:
        raise HTTPException(status_code=400, detail="No valid sequences found in FASTA file")
    
    logger.info(f"Parsed {len(sequences)} sequences from multi-FASTA")
    
    # Process each sequence
    results = []
    for seq_data in sequences:
        try:
            result = await upload_sequence(
                sequence=seq_data['sequence'],
                sequence_id=seq_data['id']
            )
            results.append(result)
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Error processing sequence {seq_data['id']}: {e}")
            results.append(SequenceResult(
                query_id=seq_data['id'],
                status="error",
                message=f"Processing failed: {str(e)}",
                method_used="BLAST+TM-align"
            ))
    
    return MultiSequenceResult(
        results=results,
        total_sequences=len(sequences),
        processed=len(results)
    )


# ============================================================================
# FRONTEND COMPATIBILITY ENDPOINTS
# ============================================================================
# These endpoints match the frontend's expected API contract

class ClassificationResult(BaseModel):
    """Classification result for frontend compatibility"""
    query_id: str
    classification: str
    tm_score: Optional[float] = None
    best_match_id: Optional[str] = None
    blast_result: Optional[dict] = None
    tm_align_result: Optional[dict] = None


class ProcessingResult(BaseModel):
    """Processing result for frontend compatibility"""
    job_id: str
    status: str
    results: List[ClassificationResult]
    completed_at: str
    alphafold_queued: Optional[bool] = False


def _store_job_result(result: ProcessingResult) -> ProcessingResult:
    """Persist a completed job result for later retrieval."""
    with _job_store_lock:
        _job_store[result.job_id] = result.model_dump()
    return result


def _init_job(job_id: str) -> None:
    """Create a placeholder job so the UI can poll immediately."""
    with _job_store_lock:
        _job_store[job_id] = ProcessingResult(
            job_id=job_id,
            status="processing",
            results=[],
            completed_at=datetime.now().isoformat(),
            alphafold_queued=False,
        ).model_dump()


def _fail_job(job_id: str, message: str) -> None:
    with _job_store_lock:
        _job_store[job_id] = ProcessingResult(
            job_id=job_id,
            status="error",
            results=[
                ClassificationResult(
                    query_id=job_id,
                    classification=f"Error: {message}",
                )
            ],
            completed_at=datetime.now().isoformat(),
            alphafold_queued=False,
        ).model_dump()


def _complete_job(job_id: str, result: ProcessingResult) -> None:
    with _job_store_lock:
        _job_store[job_id] = result.model_dump()


def _run_coroutine_in_new_loop(coro):
    """Run an async coroutine in a dedicated event loop (for background threads)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception:
            pass


def _get_pdb_path_from_structure_name(structure_name: str) -> Optional[str]:
    """
    Get full PDB file path from structure name (filename without extension).
    Returns None if not found.
    """
    if not structure_name:
        return None
    
    db_files = get_structure_database_files()
    for db_file in db_files:
        if db_file.stem == structure_name or db_file.name == structure_name:
            return str(db_file.resolve())
    
    # Try with .pdb extension
    if not structure_name.endswith('.pdb'):
        for db_file in db_files:
            if db_file.name == f"{structure_name}.pdb":
                return str(db_file.resolve())
    
    return None


def _classify_structure_result(match_result: StructureMatchResult, query_id: str) -> ClassificationResult:
    """Convert StructureMatchResult to ClassificationResult format."""
    if match_result.status == "already_in_database":
        classification = "Already in database"
    elif match_result.status == "matched":
        if match_result.tm_score and match_result.tm_score >= 0.5:
            classification = "Known structural family"
        else:
            classification = "Novel structure"
    else:
        classification = "No matches found"
    
    tm_align_result = None
    if match_result.tm_score is not None:
        tm_align_result = {
            "target_id": match_result.matched_structure or "N/A",
            "tm_score": match_result.tm_score,
            "rmsd": match_result.rmsd or 0.0,
            "alignment_length": match_result.alignment_length or 0
        }
    
    return ClassificationResult(
        query_id=query_id,
        classification=classification,
        tm_score=match_result.tm_score,
        best_match_id=match_result.matched_structure,
        tm_align_result=tm_align_result
    )


def _classify_sequence_result(seq_result: SequenceResult, query_id: str) -> ClassificationResult:
    """Convert SequenceResult to ClassificationResult format."""
    if seq_result.status == "novel_sequence":
        classification = "Novel sequence - structure prediction required"
    elif seq_result.status == "structure_missing":
        classification = "Sequence found but structure missing - structure prediction required"
    elif seq_result.status == "structure_found_no_comparison":
        classification = "Structure found but cannot compare"
    elif seq_result.status == "blast_hit_with_structure":
        if seq_result.tm_score and seq_result.tm_score >= 0.5:
            classification = "Known structural family"
        else:
            classification = "Structurally similar"
    else:
        classification = seq_result.status
    
    blast_result = None
    if seq_result.blast_hit_id:
        blast_result = {
            "hit_id": seq_result.blast_hit_id,
            "e_value": seq_result.blast_evalue or 0.0,
            "identity": seq_result.blast_identity or 0.0,
            "query_coverage": seq_result.blast_query_coverage or 0.0,
            "alignment_length": seq_result.alignment_length or 0
        }
    
    tm_align_result = None
    if seq_result.tm_score is not None:
        tm_align_result = {
            "target_id": seq_result.matched_structure or "N/A",
            "tm_score": seq_result.tm_score,
            "rmsd": seq_result.rmsd or 0.0,
            "alignment_length": seq_result.alignment_length or 0
        }
    
    return ClassificationResult(
        query_id=query_id,
        classification=classification,
        tm_score=seq_result.tm_score,
        best_match_id=seq_result.matched_structure,
        blast_result=blast_result,
        tm_align_result=tm_align_result
    )


@app.post("/api/process/structure", response_model=ProcessingResult)
async def api_process_structure(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Frontend compatibility endpoint for structure processing.
    Wraps /upload/structure and converts response format.
    """
    # Read file content once
    content = await file.read()
    filename = file.filename or "unknown"
    
    # Validate file type
    if not filename.lower().endswith(('.pdb', '.cif')):
        raise HTTPException(status_code=400, detail="File must be PDB or CIF format")

    job_id = f"struct_{uuid.uuid4().hex[:8]}"
    _init_job(job_id)
    
    # Save uploaded file temporarily (background job will clean up)
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp_file:
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    async def _do_work():
        query_filename = os.path.basename(filename)
        try:
            # If TM-align is unavailable, fall back to BLAST-only flow by extracting a
            # rough sequence from the uploaded structure and searching the DB.
            if not is_tmalign_ready():
                seq = extract_sequence_from_pdb(tmp_path)
                if not seq:
                    raise RuntimeError(
                        "TM-align unavailable and could not extract a sequence from the uploaded structure."
                    )
                seq_result = await upload_sequence(sequence=seq, sequence_id=os.path.splitext(query_filename)[0])
                classification_result = _classify_sequence_result(seq_result, query_filename)
                _complete_job(
                    job_id,
                    ProcessingResult(
                        job_id=job_id,
                        status="completed",
                        results=[classification_result],
                        completed_at=datetime.now().isoformat(),
                        alphafold_queued=seq_result.status in ["novel_sequence", "structure_missing"],
                    ),
                )
                return

            # Reuse the canonical implementation for structure uploads.
            tmp_upload = UploadFile(filename=query_filename, file=open(tmp_path, "rb"))
            try:
                match_result = await upload_structure(tmp_upload)
            finally:
                try:
                    tmp_upload.file.close()
                except Exception:
                    pass

            classification_result = _classify_structure_result(match_result, os.path.splitext(query_filename)[0])
            _complete_job(
                job_id,
                ProcessingResult(
                    job_id=job_id,
                    status="completed",
                    results=[classification_result],
                    completed_at=datetime.now().isoformat(),
                    alphafold_queued=False,
                ),
            )
        except Exception as e:
            logger.exception("Structure processing failed")
            _fail_job(job_id, str(e))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    # Run async work in background thread with its own loop.
    background_tasks.add_task(lambda: _run_coroutine_in_new_loop(_do_work()))
    return _job_store[job_id]


class SequenceRequest(BaseModel):
    """Request model for sequence processing"""
    sequence: str
    sequence_id: Optional[str] = None


@app.post("/api/process/sequence", response_model=ProcessingResult)
async def api_process_sequence(background_tasks: BackgroundTasks, request: SequenceRequest):
    """
    Frontend compatibility endpoint for sequence processing.
    Wraps /upload/sequence and converts response format.
    """
    job_id = f"seq_{uuid.uuid4().hex[:8]}"
    _init_job(job_id)

    async def _do_work():
        try:
            seq_result = await upload_sequence(request.sequence, request.sequence_id)
            query_id = seq_result.query_id or request.sequence_id or job_id
            classification_result = _classify_sequence_result(seq_result, query_id)
            alphafold_queued = seq_result.status in ["novel_sequence", "structure_missing"]
            _complete_job(
                job_id,
                ProcessingResult(
                    job_id=job_id,
                    status="completed",
                    results=[classification_result],
                    completed_at=datetime.now().isoformat(),
                    alphafold_queued=alphafold_queued,
                ),
            )
        except Exception as e:
            logger.exception("Sequence processing failed")
            _fail_job(job_id, str(e))

    background_tasks.add_task(lambda: _run_coroutine_in_new_loop(_do_work()))
    return _job_store[job_id]


@app.post("/api/process/fasta", response_model=ProcessingResult)
async def api_process_fasta(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Frontend compatibility endpoint for FASTA processing.
    Wraps /upload/multisequence and converts response format.
    """
    job_id = f"fasta_{uuid.uuid4().hex[:8]}"
    _init_job(job_id)

    # Read once because UploadFile streams are consumed.
    content = await file.read()
    filename = file.filename or "upload.fasta"

    async def _do_work():
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".fasta") as tmp_file:
                tmp_file.write(content)
                tmp_path = tmp_file.name

            tmp_upload = UploadFile(filename=filename, file=open(tmp_path, "rb"))
            try:
                multi_result = await upload_multisequence(tmp_upload)
            finally:
                try:
                    tmp_upload.file.close()
                except Exception:
                    pass

            classification_results: List[ClassificationResult] = []
            alphafold_queued = False
            for i, seq_result in enumerate(multi_result.results):
                query_id = seq_result.query_id or f"seq_{i+1}"
                classification_results.append(_classify_sequence_result(seq_result, query_id))
                if seq_result.status in ["novel_sequence", "structure_missing"]:
                    alphafold_queued = True

            _complete_job(
                job_id,
                ProcessingResult(
                    job_id=job_id,
                    status="completed",
                    results=classification_results,
                    completed_at=datetime.now().isoformat(),
                    alphafold_queued=alphafold_queued,
                ),
            )
        except Exception as e:
            logger.exception("FASTA processing failed")
            _fail_job(job_id, str(e))
        finally:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    background_tasks.add_task(lambda: _run_coroutine_in_new_loop(_do_work()))
    return _job_store[job_id]


@app.get("/api/job/{job_id}", response_model=ProcessingResult)
async def get_job(job_id: str):
    """Return a previously completed synchronous job by ID."""
    job_result = _job_store.get(job_id)
    if not job_result:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job_result


@app.get("/api/download/pdb")
async def download_pdb(structure_id: str = Query(..., min_length=1)):
    """Download a structure from the local database by structure ID."""
    pdb_path = _get_pdb_path_from_structure_name(structure_id)
    if not pdb_path:
        raise HTTPException(status_code=404, detail=f"Structure not found: {structure_id}")

    pdb_file = pathlib.Path(pdb_path)
    if not pdb_file.exists() or not pdb_file.is_file():
        raise HTTPException(status_code=404, detail=f"PDB file not found: {structure_id}")

    return FileResponse(
        path=str(pdb_file),
        media_type="chemical/x-pdb",
        filename=pdb_file.name
    )


# Startup validation: Check required binaries are available in PATH
# External tools are resolved via PATH for portability.
# This design supports Windows dev and Linux/HPC deployment.
# All validations are performed with absolute paths for robustness.
def validate_binaries():
    """
    Validate that all required binaries and databases are available at startup.
    
    Performs comprehensive checks:
    1. BLAST+ binaries (blastp, makeblastdb) - verifies execution
    2. BLAST database - auto-creates if FASTA exists but DB missing
    3. WSL availability - required for TM-align
    4. TM-align via WSL - verifies `wsl TMalign -h` works

    Raises RuntimeError with actionable messages if required BLAST components fail.
    TM-align/WSL is optional at startup; if unavailable, the API starts in degraded mode.
    """
    global BLASTP_PATH, MAKEBLASTDB_PATH, TMALIGN_PATH, WSL_AVAILABLE, WSL_DISTRO, TMALIGN_AVAILABLE
    
    logger.info("Starting backend validation...")
    
    # 1. Check BLAST+ blastp binary
    BLASTP_PATH = check_binary('blastp')
    if not BLASTP_PATH:
        raise RuntimeError(
            "BLAST+ not found in PATH.\n"
            "ACTION REQUIRED: Install BLAST+ from https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/\n"
            "Ensure blastp.exe is in your system PATH."
        )
    
    # Verify blastp works
    try:
        result = subprocess.run([BLASTP_PATH, '-version'], capture_output=True, text=True, timeout=5, check=True)
        logger.info(f"BLAST+ verified: {BLASTP_PATH}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"blastp timeout - binary may be corrupted: {BLASTP_PATH}")
    except Exception as e:
        raise RuntimeError(f"blastp found but failed to execute: {e}\nPath: {BLASTP_PATH}")
    
    # 2. Check BLAST+ makeblastdb binary
    MAKEBLASTDB_PATH = check_binary('makeblastdb')
    if not MAKEBLASTDB_PATH:
        raise RuntimeError(
            "makeblastdb not found in PATH.\n"
            "ACTION REQUIRED: Install BLAST+ from https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/\n"
            "Ensure makeblastdb.exe is in your system PATH."
        )
    
    # Verify makeblastdb works
    try:
        result = subprocess.run([MAKEBLASTDB_PATH, '-version'], capture_output=True, text=True, timeout=5, check=True)
        logger.info(f"makeblastdb verified: {MAKEBLASTDB_PATH}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"makeblastdb timeout - binary may be corrupted: {MAKEBLASTDB_PATH}")
    except Exception as e:
        raise RuntimeError(f"makeblastdb found but failed to execute: {e}\nPath: {MAKEBLASTDB_PATH}")
    
    # 3. Check TM-align via native binary first, then WSL fallback.
    TMALIGN_PATH = check_tmalign_native()
    if TMALIGN_PATH:
        TMALIGN_AVAILABLE = True
        logger.info(f"TM-align verified via native binary: {TMALIGN_PATH}")
    else:
        WSL_AVAILABLE, WSL_DISTRO = check_wsl_available()
        if not WSL_AVAILABLE:
            TMALIGN_AVAILABLE = False
            logger.warning(
                "WSL is unavailable or access is denied, and no native TM-align binary was found. "
                "Structure comparison will be disabled until TM-align access is restored."
            )
        else:
            logger.info(f"WSL verified: {WSL_DISTRO}")
            TMALIGN_AVAILABLE = check_tmalign_via_wsl()
            if TMALIGN_AVAILABLE:
                logger.info("TM-align verified via WSL")
            else:
                logger.warning(
                    "TM-align is unavailable via WSL and no native binary was found. "
                    "Structure comparison endpoints will return 503 until TM-align access is restored."
                )
    
    # 5. Ensure BLAST database is indexed (auto-creates if needed)
    logger.info("Checking BLAST database...")
    if not ensure_blast_database_indexed():
        raise RuntimeError(
            f"BLAST database indexing failed.\n"
            f"FASTA file: {SEQUENCE_DB_PATH}\n"
            f"Database prefix: {SEQUENCE_DB_INDEX_PATH}\n"
            "ACTION REQUIRED: Ensure effector_sequences.fasta exists and is valid FASTA format."
        )
    
    # 6. Verify structure database exists
    if not STRUCTURE_DB_PATH.exists():
        logger.warning(f"Structure database directory not found: {STRUCTURE_DB_PATH}")
        logger.warning("Structure uploads will fail until PDB files are available")
    else:
        structure_count = len(list(STRUCTURE_DB_PATH.glob("*.pdb")))
        logger.info(f"Structure database: {structure_count} PDB files found")
    
    # Startup self-check complete
    logger.info("=" * 70)
    logger.info("✓ Backend validation complete")
    logger.info("=" * 70)
    logger.info(f"  BLAST+: {BLASTP_PATH}")
    logger.info(f"  Database: {SEQUENCE_DB_INDEX_PATH}")
    logger.info(f"  WSL: {WSL_DISTRO if WSL_AVAILABLE else 'Unavailable'}")
    if TMALIGN_PATH:
        logger.info(f"  TM-align: Available via native binary ({TMALIGN_PATH})")
    else:
        logger.info(f"  TM-align: {'Available via WSL' if TMALIGN_AVAILABLE else 'Unavailable (degraded mode)'}")
    logger.info("=" * 70)


@app.on_event("startup")
async def startup_event():
    """
    Validate binaries and databases at application startup.
    
    Performs comprehensive validation and fails fast with actionable error messages
    if any required component is missing or misconfigured.
    """
    try:
        validate_binaries()
        logger.info("Backend startup validation complete - all systems operational")
    except RuntimeError as e:
        error_msg = f"Startup validation failed: {e}"
        logger.critical(error_msg)
        # Print to console for visibility
        print("\n" + "=" * 70)
        print("BACKEND STARTUP FAILED")
        print("=" * 70)
        print(error_msg)
        print("=" * 70 + "\n")
        raise RuntimeError(error_msg)


if __name__ == "__main__":
    """
    Main entry point for backend server.
    
    Validates all dependencies before starting the server.
    Fails fast with clear error messages if validation fails.
    """
    # Validate binaries before starting server
    try:
        validate_binaries()
        print("\n" + "=" * 70)
        print("Backend server starting...")
        print("=" * 70 + "\n")
    except RuntimeError as e:
        logger.critical(str(e))
        print("\n" + "=" * 70)
        print("BACKEND STARTUP FAILED")
        print("=" * 70)
        print(str(e))
        print("=" * 70 + "\n")
        exit(1)
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
