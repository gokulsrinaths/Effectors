"""Hosted job runner for local-demo execution."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from threading import Event, Thread

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import HostedJob
from ..schemas import JobCreateRequest
from .emailer import send_or_preview_email
from .execution import resolve_execution_mode
from .hpc_submission import refresh_hpc_job, submit_hpc_job
from .pipeline_adapter import run_real_pipeline
from .report_pdf import build_job_report_pdf

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _touch_job_heartbeat(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as heartbeat_db:
        job = heartbeat_db.get(HostedJob, job_id)
        if not job or job.status != "running":
            return
        heartbeat_at = _utcnow()
        job.last_heartbeat_at = heartbeat_at
        job.reservation_expires_at = heartbeat_at + timedelta(seconds=settings.job_lease_seconds)
        heartbeat_db.commit()


def _start_heartbeat(job_id: str) -> tuple[Event, Thread]:
    settings = get_settings()
    stop_event = Event()

    def runner() -> None:
        while not stop_event.wait(settings.job_heartbeat_seconds):
            _touch_job_heartbeat(job_id)

    thread = Thread(target=runner, name=f"job-heartbeat-{job_id[:8]}", daemon=True)
    thread.start()
    return stop_event, thread


def _mark_retry_or_failure(db: Session, job: HostedJob, exc: Exception) -> HostedJob:
    job.completed_at = _utcnow()
    job.error_message = str(exc)
    job.last_heartbeat_at = _utcnow()
    job.reservation_expires_at = None
    if job.attempt_count < job.max_attempts:
        job.status = "queued"
        job.worker_id = None
    else:
        job.status = "failed"
    db.commit()
    db.refresh(job)
    return job


def _send_completion_email(
    job: HostedJob, summary_message: str, result: dict | None = None
) -> None:
    """Mail the completion notice with the PDF report attached.

    Total by construction: the job is already committed as completed by the time
    this runs, and both call sites sit inside a broad ``except Exception`` that
    would otherwise re-queue a finished job over an SMTP timeout. Nothing in here
    may propagate.
    """
    try:
        settings = get_settings()
        if not job.email:
            return

        # Guarded separately from the send: a report problem should downgrade the
        # email to text-only, never suppress the notification entirely.
        try:
            pdf_path = build_job_report_pdf(job.id, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PDF report unavailable for job %s: %s: %s", job.id, type(exc).__name__, exc
            )
            pdf_path = None

        body = (
            "Your job finished.\n\n"
            f"Job ID: {job.id}\n"
            f"Status: {job.status}\n"
            f"Summary: {summary_message}\n"
        )
        if pdf_path:
            body += "\nA PDF report of your results is attached.\n"

        send_or_preview_email(
            email=job.email,
            subject=f"Effector job {job.id} completed",
            body=body,
            preview_dir=settings.logs_dir / "email-previews",
            attachments=[pdf_path] if pdf_path else None,
            preview_slug=job.id,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning(
            "Completion email failed for job %s: %s: %s", job.id, type(exc).__name__, exc
        )


def run_job(db: Session, job: HostedJob, request: JobCreateRequest) -> HostedJob:
    """Run one hosted job.

    Local mode executes inside the current process. HPC mode submits a remote
    Slurm job and returns immediately for later status refresh.
    """
    settings = get_settings()
    job.backend_mode = resolve_execution_mode()
    job.started_at = _utcnow()
    job.last_heartbeat_at = job.started_at
    job.reservation_expires_at = job.started_at + timedelta(seconds=settings.job_lease_seconds)
    job.attempt_count += 1
    job.error_message = None
    if job.backend_mode == "hpc":
        job.status = "submitted"
    else:
        job.status = "running"
    db.commit()
    db.refresh(job)

    input_path = Path(job.input_path)
    result_path = settings.results_dir / f"{job.id}.json"
    stop_event: Event | None = None
    heartbeat_thread: Thread | None = None

    try:
        request_payload = json.loads(input_path.read_text(encoding="utf-8"))
        if job.backend_mode == "hpc":
            job = submit_hpc_job(job, request_payload)
            db.commit()
            db.refresh(job)
            return job

        stop_event, heartbeat_thread = _start_heartbeat(job.id)
        result = run_real_pipeline(request_payload, result_path)
        job.status = "completed"
        job.result_path = str(result_path)
        job.summary_json = json.dumps(result["summary"], sort_keys=True)
        job.completed_at = _utcnow()
        job.error_message = None
        job.last_heartbeat_at = _utcnow()
        job.reservation_expires_at = None
        db.commit()
        db.refresh(job)
        _send_completion_email(job, result["summary"]["message"], result)
        return job
    except Exception as exc:  # noqa: BLE001
        return _mark_retry_or_failure(db, job, exc)
    finally:
        if stop_event is not None:
            stop_event.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)


def refresh_submitted_hpc_job(db: Session, job: HostedJob) -> HostedJob:
    """Refresh a submitted or running HPC job and pull results back when ready."""
    settings = get_settings()
    result_path = settings.results_dir / f"{job.id}.json"
    try:
        job, payload, error_message = refresh_hpc_job(job, result_path)
    except Exception as exc:  # noqa: BLE001
        return _mark_retry_or_failure(db, job, exc)

    if error_message:
        return _mark_retry_or_failure(db, job, RuntimeError(error_message))

    if payload is not None:
        job.completed_at = _utcnow()
        job.summary_json = json.dumps(payload["summary"], sort_keys=True)
        job.error_message = None
        job.reservation_expires_at = None
        db.commit()
        db.refresh(job)
        _send_completion_email(job, payload["summary"]["message"], payload)
        return job

    db.commit()
    db.refresh(job)
    return job
