"""Hosted job runner for local-demo execution."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import HostedJob
from ..schemas import JobCreateRequest
from .emailer import send_or_preview_email
from .execution import ensure_hpc_placeholder, resolve_execution_mode
from .pipeline_adapter import run_real_pipeline


def run_job(db: Session, job: HostedJob, request: JobCreateRequest) -> HostedJob:
    """Run one hosted job in local demo mode.

    In the real hosted product this function should be executed by a worker.
    """
    settings = get_settings()
    job.backend_mode = resolve_execution_mode()

    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()
    db.refresh(job)

    input_path = Path(job.input_path)
    result_path = settings.results_dir / f"{job.id}.json"

    try:
        request_payload = json.loads(input_path.read_text(encoding="utf-8"))
        if job.backend_mode == "hpc":
            ensure_hpc_placeholder(settings.logs_dir / "hpc-markers" / job.id)
            raise RuntimeError(
                "HPC execution mode is not wired yet. Set EFFECTOR_EXECUTION_MODE=local "
                "to run jobs through the current backend engine."
            )
        result = run_real_pipeline(request_payload, result_path)
        job.status = "completed"
        job.result_path = str(result_path)
        job.summary_json = json.dumps(result["summary"], sort_keys=True)
        job.completed_at = datetime.utcnow()
        job.error_message = None
        db.commit()
        db.refresh(job)

        if job.email:
            send_or_preview_email(
                email=job.email,
                subject=f"Effector job {job.id} completed",
                body=(
                    "Your job finished.\n\n"
                    f"Job ID: {job.id}\n"
                    f"Status: {job.status}\n"
                    f"Summary: {result['summary']['message']}\n"
                ),
                preview_dir=settings.logs_dir / "email-previews",
            )
        return job
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        job.error_message = str(exc)
        db.commit()
        db.refresh(job)
        return job
