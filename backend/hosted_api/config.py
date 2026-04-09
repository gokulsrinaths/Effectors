"""Configuration for the hosted effector product scaffold."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    uploads_dir: Path
    results_dir: Path
    logs_dir: Path
    email_from: str
    public_base_url: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_starttls: bool
    worker_poll_interval: float
    execution_mode: str


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
        email_from=os.getenv("EFFECTOR_EMAIL_FROM", "noreply@example.com"),
        public_base_url=os.getenv("EFFECTOR_PUBLIC_BASE_URL", "http://localhost:8000"),
        smtp_host=os.getenv("EFFECTOR_SMTP_HOST"),
        smtp_port=int(os.getenv("EFFECTOR_SMTP_PORT", "587")),
        smtp_username=os.getenv("EFFECTOR_SMTP_USERNAME"),
        smtp_password=os.getenv("EFFECTOR_SMTP_PASSWORD"),
        smtp_starttls=os.getenv("EFFECTOR_SMTP_STARTTLS", "true").lower() == "true",
        worker_poll_interval=float(os.getenv("EFFECTOR_WORKER_POLL_INTERVAL", "5")),
        execution_mode=os.getenv("EFFECTOR_EXECUTION_MODE", "local"),
    )
