"""Job routes for the hosted async-product scaffold."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import HostedJob
from ..schemas import JobCreateRequest, JobListResponse, JobResponse
from ..security import require_admin_api_key
from ..services.execution import describe_execution_mode
from ..services.job_runner import run_job


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize_job(job: HostedJob) -> JobResponse:
    summary = json.loads(job.summary_json) if job.summary_json else None
    return JobResponse(
        id=job.id,
        input_type=job.input_type,
        email=job.email,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        input_path=job.input_path,
        result_path=job.result_path,
        summary=summary,
        error_message=job.error_message,
        backend_mode=job.backend_mode,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
    )


def _write_request_payload(job_id: str, payload: dict) -> str:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    request_path = settings.uploads_dir / f"{job_id}.request.json"
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(request_path)


@router.post("", response_model=JobResponse)
def create_job(request: JobCreateRequest, db: Session = Depends(get_db)) -> JobResponse:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    if request.input_type != "sequence":
        raise HTTPException(
            status_code=400,
            detail="Use /jobs/upload for structure and FASTA file jobs.",
        )
    if not request.sequence:
        raise HTTPException(status_code=400, detail="Sequence input is required for sequence jobs.")
    if len(request.sequence) > settings.max_sequence_chars:
        raise HTTPException(status_code=400, detail="Sequence input exceeds the configured maximum length.")

    job_id = uuid4().hex
    input_path = _write_request_payload(job_id, request.model_dump())

    job = HostedJob(
        id=job_id,
        input_type=request.input_type,
        email=request.email,
        status="queued",
        input_path=str(input_path),
        backend_mode=describe_execution_mode()["mode"],
        max_attempts=settings.max_job_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.post("/upload", response_model=JobResponse)
async def create_upload_job(
    input_type: str = Form(...),
    email: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobResponse:
    if input_type not in {"structure", "fasta"}:
        raise HTTPException(status_code=400, detail="input_type must be 'structure' or 'fasta'.")

    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    job_id = uuid4().hex
    original_filename = file.filename or f"{input_type}.dat"
    file_bytes = await file.read()
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds the configured maximum size.")
    staged_path = settings.uploads_dir / f"{job_id}_{original_filename}"
    staged_path.write_bytes(file_bytes)

    payload = {
        "input_type": input_type,
        "email": email,
        "staged_path": str(staged_path),
        "original_filename": original_filename,
    }
    input_path = _write_request_payload(job_id, payload)

    job = HostedJob(
        id=job_id,
        input_type=input_type,
        email=email,
        status="queued",
        input_path=input_path,
        backend_mode=describe_execution_mode()["mode"],
        max_attempts=settings.max_job_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.get("", response_model=JobListResponse, dependencies=[Depends(require_admin_api_key)])
def list_jobs(db: Session = Depends(get_db)) -> JobListResponse:
    jobs = db.query(HostedJob).order_by(HostedJob.created_at.desc()).all()
    return JobListResponse(items=[_serialize_job(job) for job in jobs])


@router.get("/mode")
def get_mode() -> dict:
    return describe_execution_mode()


@router.get("/results/{job_id}")
def get_result(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(HostedJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    if not job.result_path:
        raise HTTPException(status_code=404, detail=f"No result available for job: {job_id}")

    result_path = Path(job.result_path)
    if not result_path.exists():
        raise HTTPException(status_code=404, detail=f"Result file missing for job: {job_id}")
    return json.loads(result_path.read_text(encoding="utf-8"))


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(HostedJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return _serialize_job(job)


@router.post("/{job_id}/run", response_model=JobResponse, dependencies=[Depends(require_admin_api_key)])
def run_job_now(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    """Local demo trigger for the hosted scaffold.

    This endpoint should be replaced by a worker process in the real hosted product.
    """
    job = db.get(HostedJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    request_path = Path(job.input_path)
    request = JobCreateRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    job = run_job(db, job, request)
    return _serialize_job(job)
