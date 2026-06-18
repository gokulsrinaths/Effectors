"""Configuration for the hosted effector product scaffold."""

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

# Load .env from the repo root (backend/hosted_api/.env or project root .env)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on OS environment variables


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    uploads_dir: Path
    results_dir: Path
    logs_dir: Path
    cors_allowed_origins: tuple[str, ...]
    email_from: str
    public_base_url: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_starttls: bool
    worker_poll_interval: float
    job_lease_seconds: int
    job_heartbeat_seconds: int
    execution_mode: str
    max_upload_bytes: int
    max_sequence_chars: int
    max_job_attempts: int
    rate_limit_window_seconds: int
    rate_limit_create_job_limit: int
    admin_api_key: str | None
    hpc_ssh_bin: str
    hpc_scp_bin: str
    hpc_ssh_args: str
    hpc_scp_args: str
    hpc_remote_host_alias: str
    hpc_remote_effectors_root: str
    hpc_remote_runs_root: str
    hpc_remote_results_root: str
    hpc_remote_logs_root: str
    hpc_slurm_account: str
    hpc_slurm_partition: str
    hpc_slurm_partition_gpu: str
    hpc_slurm_time: str
    hpc_slurm_mem: str
    hpc_slurm_cpus: int
    hpc_slurm_gpus: int
    hpc_slurm_gpus_alphafold: int
    hpc_job_prologue: str
    hpc_job_epilogue: str
    hpc_python_bin: str
    alphafold_bin: str
    alphafold_args: str


def _parse_origins(raw_value: str) -> tuple[str, ...]:
    origins = tuple(origin.strip() for origin in raw_value.split(",") if origin.strip())
    return origins or ("http://localhost:3000",)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    data_root = root / "backend" / "hosted_api" / "data"
    uploads_dir = data_root / "uploads"
    results_dir = data_root / "results"
    logs_dir = data_root / "logs"

    return Settings(
        app_name=os.getenv("EFFECTOR_HOSTED_APP_NAME", "Effector Hosted API"),
        database_url=os.getenv(
            "EFFECTOR_HOSTED_DATABASE_URL",
            f"sqlite:///{(data_root / 'jobs.db').as_posix()}",
        ),
        uploads_dir=uploads_dir,
        results_dir=results_dir,
        logs_dir=logs_dir,
        cors_allowed_origins=_parse_origins(
            os.getenv("EFFECTOR_CORS_ALLOWED_ORIGINS", "http://localhost:3000")
        ),
        email_from=os.getenv("EFFECTOR_EMAIL_FROM", "noreply@example.com"),
        public_base_url=os.getenv("EFFECTOR_PUBLIC_BASE_URL", "http://localhost:8000"),
        smtp_host=os.getenv("EFFECTOR_SMTP_HOST"),
        smtp_port=int(os.getenv("EFFECTOR_SMTP_PORT", "587")),
        smtp_username=os.getenv("EFFECTOR_SMTP_USERNAME"),
        smtp_password=os.getenv("EFFECTOR_SMTP_PASSWORD"),
        smtp_starttls=os.getenv("EFFECTOR_SMTP_STARTTLS", "true").lower() == "true",
        worker_poll_interval=float(os.getenv("EFFECTOR_WORKER_POLL_INTERVAL", "5")),
        job_lease_seconds=int(os.getenv("EFFECTOR_JOB_LEASE_SECONDS", "900")),
        job_heartbeat_seconds=int(os.getenv("EFFECTOR_JOB_HEARTBEAT_SECONDS", "15")),
        execution_mode=os.getenv("EFFECTOR_EXECUTION_MODE", "local"),
        max_upload_bytes=int(os.getenv("EFFECTOR_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
        max_sequence_chars=int(os.getenv("EFFECTOR_MAX_SEQUENCE_CHARS", "200000")),
        max_job_attempts=int(os.getenv("EFFECTOR_MAX_JOB_ATTEMPTS", "2")),
        rate_limit_window_seconds=int(os.getenv("EFFECTOR_RATE_LIMIT_WINDOW_SECONDS", "60")),
        rate_limit_create_job_limit=int(os.getenv("EFFECTOR_RATE_LIMIT_CREATE_JOB_LIMIT", "30")),
        admin_api_key=os.getenv("EFFECTOR_ADMIN_API_KEY"),
        hpc_ssh_bin=os.getenv("EFFECTOR_HPC_SSH_BIN", "ssh"),
        hpc_scp_bin=os.getenv("EFFECTOR_HPC_SCP_BIN", "scp"),
        hpc_ssh_args=os.getenv("EFFECTOR_HPC_SSH_ARGS", ""),
        hpc_scp_args=os.getenv("EFFECTOR_HPC_SCP_ARGS", ""),
        hpc_remote_host_alias=os.getenv("EFFECTOR_HPC_REMOTE_HOST", "medicinebow"),
        hpc_remote_effectors_root=os.getenv(
            "EFFECTOR_HPC_REMOTE_EFFECTORS_ROOT",
            "/home/gokulsrinathseetharam/projects/Effectors",
        ),
        hpc_remote_runs_root=os.getenv(
            "EFFECTOR_HPC_REMOTE_RUNS_ROOT",
            "/gscratch/gokulsrinathseetharam/runs/effectors",
        ),
        hpc_remote_results_root=os.getenv(
            "EFFECTOR_HPC_REMOTE_RESULTS_ROOT",
            "/gscratch/gokulsrinathseetharam/results/effectors",
        ),
        hpc_remote_logs_root=os.getenv(
            "EFFECTOR_HPC_REMOTE_LOGS_ROOT",
            "/gscratch/gokulsrinathseetharam/logs/effectors",
        ),
        hpc_slurm_account=os.getenv("EFFECTOR_HPC_SLURM_ACCOUNT", "effectorfold"),
        hpc_slurm_partition=os.getenv("EFFECTOR_HPC_SLURM_PARTITION", ""),
        hpc_slurm_partition_gpu=os.getenv("EFFECTOR_HPC_SLURM_PARTITION_GPU", "teton-gpu"),
        hpc_slurm_time=os.getenv("EFFECTOR_HPC_SLURM_TIME", "01:00:00"),
        hpc_slurm_mem=os.getenv("EFFECTOR_HPC_SLURM_MEM", "8G"),
        hpc_slurm_cpus=int(os.getenv("EFFECTOR_HPC_SLURM_CPUS", "2")),
        hpc_slurm_gpus=int(os.getenv("EFFECTOR_HPC_SLURM_GPUS", "0")),
        hpc_slurm_gpus_alphafold=int(os.getenv("EFFECTOR_HPC_SLURM_GPUS_ALPHAFOLD", "1")),
        hpc_job_prologue=os.getenv("EFFECTOR_HPC_JOB_PROLOGUE", ""),
        hpc_job_epilogue=os.getenv("EFFECTOR_HPC_JOB_EPILOGUE", ""),
        hpc_python_bin=os.getenv("EFFECTOR_HPC_PYTHON_BIN", "python3"),
        alphafold_bin=os.getenv("EFFECTOR_ALPHAFOLD_BIN", "colabfold_batch"),
        alphafold_args=os.getenv("EFFECTOR_ALPHAFOLD_ARGS", ""),
    )
