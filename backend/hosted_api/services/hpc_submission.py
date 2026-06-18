"""SSH/Slurm helpers for hosted HPC execution mode."""

from __future__ import annotations

from datetime import datetime
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from ..config import get_settings
from ..models import HostedJob


SBATCH_ID_RE = re.compile(r"Submitted batch job (\d+)")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _remote_exec(command: str) -> subprocess.CompletedProcess[str]:
    settings = get_settings()
    ssh_args = shlex.split(settings.hpc_ssh_args) if settings.hpc_ssh_args else []
    # Run commands through bash so pipelines / compound commands behave
    # consistently across clusters (and to match diagnostics behavior).
    remote_command = "bash -lc " + shlex.quote(command)
    return subprocess.run(
        [settings.hpc_ssh_bin, *ssh_args, settings.hpc_remote_host_alias, remote_command],
        check=True,
        text=True,
        capture_output=True,
    )


def _remote_copy_text(remote_path: str, text_payload: str) -> None:
    settings = get_settings()
    scp_args = shlex.split(settings.hpc_scp_args) if settings.hpc_scp_args else []
    # Write binary so Windows doesn't convert \n → \r\n (sbatch rejects CRLF scripts).
    payload_bytes = text_payload.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        handle.write(payload_bytes)
        local_path = Path(handle.name)
    try:
        subprocess.run(
            [
                settings.hpc_scp_bin,
                *scp_args,
                str(local_path),
                f"{settings.hpc_remote_host_alias}:{remote_path}",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
    finally:
        local_path.unlink(missing_ok=True)


def _remote_copy_file(local_path: Path, remote_path: str) -> None:
    settings = get_settings()
    scp_args = shlex.split(settings.hpc_scp_args) if settings.hpc_scp_args else []
    subprocess.run(
        [settings.hpc_scp_bin, *scp_args, str(local_path), f"{settings.hpc_remote_host_alias}:{remote_path}"],
        check=True,
        text=True,
        capture_output=True,
    )


def _copy_remote_file(remote_path: str, local_path: Path) -> None:
    settings = get_settings()
    scp_args = shlex.split(settings.hpc_scp_args) if settings.hpc_scp_args else []
    local_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [settings.hpc_scp_bin, *scp_args, f"{settings.hpc_remote_host_alias}:{remote_path}", str(local_path)],
        check=True,
        text=True,
        capture_output=True,
    )


def _render_slurm_script(job: HostedJob, remote_request_path: str, *, run_alphafold: bool) -> str:
    settings = get_settings()
    partition_line = (
        f"#SBATCH --partition={settings.hpc_slurm_partition}\n" if settings.hpc_slurm_partition else ""
    )
    gpus = settings.hpc_slurm_gpus_alphafold if run_alphafold else settings.hpc_slurm_gpus
    gpu_line = f"#SBATCH --gres=gpu:{gpus}\n" if gpus > 0 else ""
    # AlphaFold needs a GPU partition; regular jobs use the CPU partition
    active_partition = (
        settings.hpc_slurm_partition_gpu if (run_alphafold and gpus > 0)
        else settings.hpc_slurm_partition
    )
    partition_line = f"#SBATCH --partition={active_partition}\n" if active_partition else ""
    remote_result_path = job.remote_result_path or ""
    remote_stdout_path = job.remote_stdout_path or ""
    remote_stderr_path = job.remote_stderr_path or ""
    remote_repo_root = settings.hpc_remote_effectors_root
    prologue = (settings.hpc_job_prologue or "").rstrip()
    epilogue = (settings.hpc_job_epilogue or "").rstrip()
    prologue_block = f"\n{prologue}\n" if prologue else "\n"
    epilogue_block = f"\n{epilogue}\n" if epilogue else "\n"
    alphafold_exports = (
        "\n".join(
            line
            for line in [
                f"export EFFECTOR_ALPHAFOLD_BIN={shlex.quote(settings.alphafold_bin)}",
                f"export EFFECTOR_ALPHAFOLD_ARGS={shlex.quote(settings.alphafold_args)}",
                f"export EFFECTOR_CHIMERAX_BIN={shlex.quote(settings.chimerax_bin)}",
            ]
            if line
        )
        + "\n"
    )

    return f"""#!/bin/bash
#SBATCH --job-name=effectors-{job.input_type}
#SBATCH --output={remote_stdout_path}
#SBATCH --error={remote_stderr_path}
#SBATCH --time={settings.hpc_slurm_time}
#SBATCH --mem={settings.hpc_slurm_mem}
#SBATCH --cpus-per-task={settings.hpc_slurm_cpus}
#SBATCH --account={settings.hpc_slurm_account}
{partition_line}{gpu_line}set -euo pipefail
{prologue_block}{alphafold_exports}

REMOTE_REPO_ROOT={shlex.quote(remote_repo_root)}
REMOTE_REQUEST_PATH={shlex.quote(remote_request_path)}
REMOTE_RESULT_PATH={shlex.quote(remote_result_path)}

mkdir -p "$(dirname "$REMOTE_RESULT_PATH")"
cd "$REMOTE_REPO_ROOT"
{settings.hpc_python_bin} backend/hosted_api/remote_runner.py \
  --request "$REMOTE_REQUEST_PATH" \
  --result "$REMOTE_RESULT_PATH"
{epilogue_block}
"""


def submit_hpc_job(job: HostedJob, request_payload: dict) -> HostedJob:
    settings = get_settings()
    remote_run_dir = f"{settings.hpc_remote_runs_root}/{job.id}"
    remote_result_path = f"{settings.hpc_remote_results_root}/{job.id}/result.json"
    remote_stdout_path = f"{settings.hpc_remote_logs_root}/{job.id}.out"
    remote_stderr_path = f"{settings.hpc_remote_logs_root}/{job.id}.err"
    remote_request_path = f"{remote_run_dir}/request.json"
    remote_script_path = f"{remote_run_dir}/job.slurm"

    request_payload = dict(request_payload)
    staged_path = request_payload.get("staged_path")
    original_filename = request_payload.get("original_filename")
    if staged_path and original_filename:
        remote_input_path = f"{remote_run_dir}/{Path(original_filename).name}"
        _remote_exec(
            "mkdir -p "
            + " ".join(
                shlex.quote(path)
                for path in [
                    settings.hpc_remote_runs_root,
                    settings.hpc_remote_results_root,
                    settings.hpc_remote_logs_root,
                    remote_run_dir,
                    str(Path(remote_result_path).parent).replace("\\", "/"),
                ]
            )
        )
        _remote_copy_file(Path(staged_path), remote_input_path)
        request_payload["staged_path"] = remote_input_path
    else:
        _remote_exec(
            "mkdir -p "
            + " ".join(
                shlex.quote(path)
                for path in [
                    settings.hpc_remote_runs_root,
                    settings.hpc_remote_results_root,
                    settings.hpc_remote_logs_root,
                    remote_run_dir,
                    str(Path(remote_result_path).parent).replace("\\", "/"),
                ]
            )
        )

    # Set paths on job BEFORE rendering the script so _render_slurm_script can read them.
    job.remote_run_dir = remote_run_dir
    job.remote_result_path = remote_result_path
    job.remote_stdout_path = remote_stdout_path
    job.remote_stderr_path = remote_stderr_path

    _remote_copy_text(remote_request_path, json.dumps(request_payload, indent=2, sort_keys=True) + "\n")
    # Force Unix line endings — sbatch rejects CRLF scripts from Windows machines.
    slurm_script = _render_slurm_script(
        job, remote_request_path, run_alphafold=bool(request_payload.get("run_alphafold"))
    ).replace("\r\n", "\n").replace("\r", "\n")
    _remote_copy_text(remote_script_path, slurm_script)
    _remote_exec(f"chmod 700 {shlex.quote(remote_script_path)}")

    submit_result = _remote_exec(
        f"sbatch -A {shlex.quote(settings.hpc_slurm_account)} {shlex.quote(remote_script_path)}"
    )
    match = SBATCH_ID_RE.search(submit_result.stdout)
    if not match:
        raise RuntimeError(f"Unable to parse sbatch output: {submit_result.stdout.strip()}")

    job.remote_job_id = match.group(1)
    job.status = "submitted"
    job.last_heartbeat_at = _utcnow()
    job.reservation_expires_at = None
    return job


def refresh_hpc_job(job: HostedJob, local_result_path: Path) -> tuple[HostedJob, dict | None, str | None]:
    if not job.remote_job_id:
        return job, None, None

    # Prefer sacct (historical accounting), but fall back to squeue if the
    # accounting record hasn't shown up yet.
    line = ""
    try:
        status_result = _remote_exec(
            (
                f"sacct -j {shlex.quote(job.remote_job_id)} "
                "--noheader --parsable2 --format=State,ExitCode | head -n 1"
            )
        )
        line = status_result.stdout.strip()
    except subprocess.CalledProcessError:
        line = ""

    if not line:
        try:
            squeue_result = _remote_exec(
                f"squeue -j {shlex.quote(job.remote_job_id)} -h -o %T | head -n 1"
            )
            state = squeue_result.stdout.strip()
        except subprocess.CalledProcessError:
            state = ""
        if not state:
            return job, None, None
        normalized_state = state.upper()
        if normalized_state in {"PENDING", "CONFIGURING", "SUSPENDED"}:
            job.status = "submitted"
            return job, None, None
        if normalized_state in {"RUNNING", "COMPLETING"}:
            job.status = "running"
            job.last_heartbeat_at = _utcnow()
            return job, None, None
        return job, None, None

    state, _, exit_code = line.partition("|")
    normalized_state = state.upper()
    if normalized_state in {"PENDING", "CONFIGURING", "SUSPENDED"}:
        job.status = "submitted"
        return job, None, None
    if normalized_state in {"RUNNING", "COMPLETING"}:
        job.status = "running"
        job.last_heartbeat_at = _utcnow()
        return job, None, None
    if normalized_state == "COMPLETED":
        if not job.remote_result_path:
            raise RuntimeError("Remote result path missing for completed HPC job.")
        _copy_remote_file(job.remote_result_path, local_result_path)
        payload = json.loads(local_result_path.read_text(encoding="utf-8"))
        alphafold = payload.get("alphafold") if isinstance(payload, dict) else None
        if isinstance(alphafold, dict) and alphafold.get("status") == "completed" and alphafold.get("pdb_remote_path"):
            remote_pdb_path = str(alphafold["pdb_remote_path"])
            local_pdb_path = local_result_path.parent / f"{job.id}.alphafold.pdb"
            _copy_remote_file(remote_pdb_path, local_pdb_path)
            alphafold["pdb_local_path"] = str(local_pdb_path)
            payload["alphafold"] = alphafold
        remote_image_path = payload.get("structure_image_path") if isinstance(payload, dict) else None
        if remote_image_path:
            local_image_path = local_result_path.parent / f"{job.id}.structure.png"
            try:
                _copy_remote_file(remote_image_path, local_image_path)
                payload["structure_image_local_path"] = str(local_image_path)
            except Exception:
                pass  # rendering may have been skipped on HPC — not fatal
        if alphafold or remote_image_path:
            local_result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        job.status = "completed"
        job.result_path = str(local_result_path)
        job.last_heartbeat_at = _utcnow()
        return job, payload, None

    job.status = "failed"
    error_message = f"Remote Slurm state {state or 'UNKNOWN'} exit={exit_code or 'n/a'}"
    return job, None, error_message
