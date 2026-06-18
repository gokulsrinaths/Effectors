"""Remote HPC diagnostics for the hosted backend.

These checks run from the API host (the machine running FastAPI) and validate:
- SSH connectivity to the configured remote host alias
- Slurm tooling availability (sbatch/sacct)
- Remote repo path exists and contains the expected entrypoint
- AlphaFold/ColabFold binary availability under the configured prologue

This is intentionally lightweight and best-effort; clusters differ in module
systems and login shells.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Any

from ..config import get_settings


def _remote_exec(remote_command: str) -> subprocess.CompletedProcess[str]:
    settings = get_settings()
    ssh_args = shlex.split(settings.hpc_ssh_args) if settings.hpc_ssh_args else []
    return subprocess.run(  # noqa: S603
        [
            settings.hpc_ssh_bin,
            *ssh_args,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            settings.hpc_remote_host_alias,
            remote_command,
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def run_hpc_diagnostics() -> dict[str, Any]:
    settings = get_settings()
    prologue = (settings.hpc_job_prologue or "").strip()
    prologue_one_liner = " ; ".join(
        line.strip().rstrip(";") for line in prologue.splitlines() if line.strip()
    )
    prologue_prefix = f"{prologue_one_liner} ; " if prologue_one_liner else ""

    remote_repo = settings.hpc_remote_effectors_root
    alphafold_bin = settings.alphafold_bin

    cmd = (
        "set -euo pipefail ; "
        + prologue_prefix
        + "echo \"host=$(hostname)\" ; "
        + "echo \"user=$(whoami)\" ; "
        + "command -v sbatch >/dev/null 2>&1 && echo \"sbatch=ok\" || echo \"sbatch=missing\" ; "
        + "command -v sacct >/dev/null 2>&1 && echo \"sacct=ok\" || echo \"sacct=missing\" ; "
        + f"test -d {shlex.quote(remote_repo)} && echo \"repo_dir=ok\" || echo \"repo_dir=missing\" ; "
        + f"test -f {shlex.quote(remote_repo + '/backend/hosted_api/remote_runner.py')} "
        + "&& echo \"remote_runner=ok\" || echo \"remote_runner=missing\" ; "
        # For compound commands (e.g. "apptainer exec ... colabfold_batch"), check
        # the first token only — that's the actual executable.
        + f"command -v {shlex.quote(alphafold_bin.split()[0])} >/dev/null 2>&1 "
        + "&& echo \"alphafold_bin=ok\" || echo \"alphafold_bin=missing\" ; "
        + "command -v python3 >/dev/null 2>&1 && echo \"python3=ok\" || echo \"python3=missing\" ; "
        + "command -v bash >/dev/null 2>&1 && echo \"bash=ok\" || echo \"bash=missing\" ; "
        + "true"
    )

    completed = _remote_exec("bash -lc " + shlex.quote(cmd))
    return {
        "remote_host_alias": settings.hpc_remote_host_alias,
        "remote_repo_root": remote_repo,
        "alphafold_bin": alphafold_bin,
        "prologue_configured": bool(prologue),
        "prologue_one_liner": prologue_one_liner or None,
        "ssh_exit_code": completed.returncode,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
        "ok": completed.returncode == 0,
    }
