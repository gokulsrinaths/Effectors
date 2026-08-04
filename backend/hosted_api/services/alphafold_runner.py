"""AlphaFold/ColabFold execution helpers for HPC jobs.

The hosted scaffold supports running AlphaFold-like tools remotely via Slurm.
We intentionally keep this as a thin wrapper around an external binary so the
cluster environment (modules/conda) can be managed in the Slurm prologue.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess


def _write_fasta(sequence_id: str, sequence: str, fasta_path: Path) -> None:
    fasta_path.parent.mkdir(parents=True, exist_ok=True)
    fasta_path.write_text(f">{sequence_id}\n{sequence.strip()}\n", encoding="utf-8")


def _pick_predicted_pdb(output_dir: Path) -> Path | None:
    """Return the highest-pLDDT model (rank_001 in ColabFold naming)."""
    if not output_dir.exists():
        return None
    candidates = list(output_dir.rglob("*.pdb"))
    if not candidates:
        return None
    # ColabFold names models: *_rank_001_*.pdb (rank 1 = highest pLDDT)
    rank1 = [p for p in candidates if "rank_001" in p.name or "rank_1" in p.name]
    if rank1:
        return rank1[0]
    # Fallback: alphabetical first (001 < 002 so still rank 1)
    return sorted(candidates)[0]


def _mean_plddt(pdb_path: Path) -> float | None:
    """Mean pLDDT of a ColabFold model.

    ColabFold writes each residue's pLDDT confidence into the B-factor column of
    the PDB, so the per-model confidence is the mean B-factor over CA atoms.
    Returns None if the column can't be read.
    """
    try:
        total = 0.0
        count = 0
        for line in pdb_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            # Average over CA atoms only — one value per residue, matching how
            # ColabFold reports pLDDT.
            if line.startswith("ATOM") and line[12:16].strip() == "CA":
                try:
                    total += float(line[60:66])
                    count += 1
                except ValueError:
                    continue
        if count == 0:
            return None
        return round(total / count, 2)
    except OSError:
        return None


def run_alphafold_prediction(*, sequence_id: str, sequence: str, output_dir: Path) -> dict:
    """Run an AlphaFold-like prediction using an external CLI.

    Default assumes ColabFold is installed and available as `colabfold_batch`.
    Configure via env vars inside the Slurm job environment:

    - EFFECTOR_ALPHAFOLD_BIN (default: colabfold_batch)
    - EFFECTOR_ALPHAFOLD_ARGS (optional additional args)
    """
    alphafold_bin = os.getenv("EFFECTOR_ALPHAFOLD_BIN", "colabfold_batch")
    extra_args = os.getenv("EFFECTOR_ALPHAFOLD_ARGS", "").strip()

    fasta_path = output_dir / f"{sequence_id}.fasta"
    _write_fasta(sequence_id, sequence, fasta_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build the full shell command string with positional args appended.
    # We use bash -c so that:
    #   1. Compound commands like "apptainer exec --nv $CF_SIF colabfold_batch" work.
    #   2. Shell variables set by module-load (e.g. $CF_SIF, $CF_CACHE) are expanded.
    positional = f"{shlex.quote(str(fasta_path))} {shlex.quote(str(output_dir))}"
    extra = f" {extra_args}" if extra_args else ""
    shell_cmd = f"{alphafold_bin} {positional}{extra}"

    try:
        completed = subprocess.run(
            ["bash", "-c", shell_cmd],
            check=True,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        return {
            "requested": True,
            "status": "failed",
            "tool": alphafold_bin,
            "output_dir": str(output_dir),
            "error_message": f"AlphaFold binary not found: {exc}",
        }
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = stderr or stdout or str(exc)
        return {
            "requested": True,
            "status": "failed",
            "tool": alphafold_bin,
            "output_dir": str(output_dir),
            "error_message": message,
        }

    predicted = _pick_predicted_pdb(output_dir)
    if not predicted:
        return {
            "requested": True,
            "status": "failed",
            "tool": alphafold_bin,
            "output_dir": str(output_dir),
            "error_message": "AlphaFold run completed but no PDB output was found.",
        }

    return {
        "requested": True,
        "status": "completed",
        "tool": alphafold_bin,
        "output_dir": str(output_dir),
        "pdb_local_path": str(predicted),
        "mean_plddt": _mean_plddt(predicted),
        "stdout": (completed.stdout or "").strip(),
    }

