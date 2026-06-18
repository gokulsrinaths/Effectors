"""Simple DB-polling worker for hosted jobs.

Run this as a separate process. It polls for queued jobs and executes them using
the hosted job runner. This keeps the API responsive and provides the minimum
background-worker shape needed before introducing Redis or HPC submission.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import socket
import time
from uuid import uuid4

from sqlalchemy import or_, select

from .config import get_settings
from .db import SessionLocal, init_db
from .models import HostedJob
from .schemas import JobCreateRequest
from .services.job_runner import refresh_submitted_hpc_job, run_job


def reserve_next_job(worker_id: str) -> HostedJob | None:
    """Claim one queued job for this worker."""
    settings = get_settings()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)

    with SessionLocal() as db:
        candidate_ids = db.execute(
            select(HostedJob.id)
            .where(
                or_(
                    HostedJob.status == "queued",
                    (
                        HostedJob.status.in_(["reserved", "running"])
                        & HostedJob.reservation_expires_at.is_not(None)
                        & (HostedJob.reservation_expires_at < now)
                    ),
                )
            )
            .order_by(HostedJob.created_at.asc())
        ).scalars().all()
        for job_id in candidate_ids:
            updated = (
                db.query(HostedJob)
                .filter(HostedJob.id == job_id)
                .filter(
                    or_(
                        HostedJob.status == "queued",
                        (
                            HostedJob.status.in_(["reserved", "running"])
                            & HostedJob.reservation_expires_at.is_not(None)
                            & (HostedJob.reservation_expires_at < now)
                        ),
                    )
                )
                .update(
                    {
                        HostedJob.status: "reserved",
                        HostedJob.worker_id: worker_id,
                        HostedJob.last_heartbeat_at: now,
                        HostedJob.reservation_expires_at: lease_expires_at,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if updated:
                return db.get(HostedJob, job_id)
        return None


def execute_reserved_job(job_id: str) -> None:
    """Load a reserved job and execute it."""
    with SessionLocal() as db:
        job = db.get(HostedJob, job_id)
        if not job:
            return
        with open(job.input_path, encoding="utf-8") as handle:
            request = JobCreateRequest.model_validate_json(handle.read())
        run_job(db, job, request)


def refresh_active_hpc_jobs() -> None:
    with SessionLocal() as db:
        active_jobs = (
            db.query(HostedJob)
            .filter(HostedJob.remote_job_id.is_not(None))
            .filter(HostedJob.status.in_(["submitted", "running"]))
            .order_by(HostedJob.created_at.asc())
            .all()
        )
        for job in active_jobs:
            refresh_submitted_hpc_job(db, job)


def main() -> None:
    settings = get_settings()
    init_db()
    worker_id = f"{socket.gethostname()}-{uuid4().hex[:8]}"
    print(f"worker_id={worker_id}")
    print(f"poll_interval={settings.worker_poll_interval}")
    print(f"execution_mode={settings.execution_mode}")

    while True:
        refresh_active_hpc_jobs()
        job = reserve_next_job(worker_id)
        if job:
            print(f"running_job={job.id}")
            execute_reserved_job(job.id)
        else:
            time.sleep(settings.worker_poll_interval)


if __name__ == "__main__":
    main()
