"""Simple DB-polling worker for hosted jobs.

Run this as a separate process. It polls for queued jobs and executes them using
the hosted job runner. This keeps the API responsive and provides the minimum
background-worker shape needed before introducing Redis or HPC submission.
"""

from __future__ import annotations

import socket
import time
from uuid import uuid4

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .models import HostedJob
from .schemas import JobCreateRequest
from .services.job_runner import run_job


def reserve_next_job(worker_id: str) -> HostedJob | None:
    """Claim one queued job for this worker."""
    with SessionLocal() as db:
        job = db.execute(
            select(HostedJob)
            .where(HostedJob.status == "queued")
            .order_by(HostedJob.created_at.asc())
        ).scalars().first()
        if not job:
            return None
        job.status = "reserved"
        job.worker_id = worker_id
        db.commit()
        db.refresh(job)
        return job


def execute_reserved_job(job_id: str) -> None:
    """Load a reserved job and execute it."""
    with SessionLocal() as db:
        job = db.get(HostedJob, job_id)
        if not job:
            return
        request = JobCreateRequest.model_validate_json(
            open(job.input_path, encoding="utf-8").read()
        )
        run_job(db, job, request)


def main() -> None:
    settings = get_settings()
    init_db()
    worker_id = f"{socket.gethostname()}-{uuid4().hex[:8]}"
    print(f"worker_id={worker_id}")
    print(f"poll_interval={settings.worker_poll_interval}")
    print(f"execution_mode={settings.execution_mode}")

    while True:
        job = reserve_next_job(worker_id)
        if job:
            print(f"running_job={job.id}")
            execute_reserved_job(job.id)
        else:
            time.sleep(settings.worker_poll_interval)


if __name__ == "__main__":
    main()
