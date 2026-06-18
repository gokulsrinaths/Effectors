"""Job routes for the hosted async-product scaffold."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import re as _re

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

_AA_RE = _re.compile(r'^[ACDEFGHIKLMNPQRSTVWYBXZUO\-\s]+$', _re.IGNORECASE)
_EMAIL_RE = _re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

from ..config import get_settings
from ..db import get_db
from ..models import HostedJob
from ..schemas import JobCreateRequest, JobListResponse, JobResponse
from ..security import hash_job_access_token, is_admin_request, issue_job_access_token, require_admin_api_key
from ..services.execution import describe_execution_mode
from ..services.job_runner import run_job
from ..services.rate_limit import enforce_create_job_rate_limit
from ..services.hpc_diagnostics import run_hpc_diagnostics


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize_job(job: HostedJob, *, access_token: str | None = None) -> JobResponse:
    summary = json.loads(job.summary_json) if job.summary_json else None
    return JobResponse(
        id=job.id,
        input_type=job.input_type,
        email=job.email,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        summary=summary,
        error_message=job.error_message,
        backend_mode=job.backend_mode,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        has_result=bool(job.result_path),
        poll_path=f"/jobs/{job.id}",
        result_path=f"/jobs/results/{job.id}" if job.result_path else None,
        access_token=access_token,
        remote_job_id=job.remote_job_id,
    )


def _write_request_payload(job_id: str, payload: dict) -> str:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    request_path = settings.uploads_dir / f"{job_id}.request.json"
    request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(request_path)


def _validate_upload_filename(input_type: str, filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    allowed = {".pdb", ".cif"} if input_type == "structure" else {".fasta", ".fa", ".fas"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{suffix or '<none>'}' for {input_type} jobs.",
        )


def _get_job_with_access(
    db: Session,
    job_id: str,
    x_job_token: str | None,
    x_api_key: str | None,
) -> HostedJob:
    job = db.get(HostedJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if is_admin_request(x_api_key):
        return job
    if not x_job_token:
        raise HTTPException(status_code=401, detail="Missing job access token.")
    if hash_job_access_token(x_job_token) != job.access_token_hash:
        raise HTTPException(status_code=403, detail="Invalid job access token.")
    return job


@router.post("", response_model=JobResponse)
def create_job(
    request: JobCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> JobResponse:
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    enforce_create_job_rate_limit(http_request)

    if request.input_type != "sequence":
        raise HTTPException(
            status_code=400,
            detail="Use /jobs/upload for structure and FASTA file jobs.",
        )
    if not request.sequence:
        raise HTTPException(status_code=400, detail="Sequence input is required for sequence jobs.")
    if len(request.sequence) > settings.max_sequence_chars:
        raise HTTPException(status_code=400, detail="Sequence input exceeds the configured maximum length.")
    clean_seq = request.sequence.replace(" ", "").replace("\n", "").replace("\r", "")
    if not _AA_RE.match(clean_seq):
        raise HTTPException(status_code=400, detail="Sequence contains invalid characters. Only standard amino acid letters are accepted.")
    if request.email and not _EMAIL_RE.match(request.email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")

    job_id = uuid4().hex
    access_token = issue_job_access_token()
    payload = request.model_dump()
    payload["job_id"] = job_id
    input_path = _write_request_payload(job_id, payload)

    job = HostedJob(
        id=job_id,
        input_type=request.input_type,
        email=request.email,
        access_token_hash=hash_job_access_token(access_token),
        status="queued",
        input_path=str(input_path),
        backend_mode=describe_execution_mode()["mode"],
        max_attempts=settings.max_job_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job, access_token=access_token)


@router.post("/upload", response_model=JobResponse)
async def create_upload_job(
    http_request: Request,
    input_type: str = Form(...),
    email: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobResponse:
    if input_type not in {"structure", "fasta"}:
        raise HTTPException(status_code=400, detail="input_type must be 'structure' or 'fasta'.")
    if email and not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address format.")

    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    enforce_create_job_rate_limit(http_request)

    job_id = uuid4().hex
    original_filename = file.filename or f"{input_type}.dat"
    _validate_upload_filename(input_type, original_filename)
    file_bytes = await file.read()
    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds the configured maximum size.")
    staged_path = settings.uploads_dir / f"{job_id}_{original_filename}"
    staged_path.write_bytes(file_bytes)

    payload = {
        "job_id": job_id,
        "input_type": input_type,
        "email": email,
        "staged_path": str(staged_path),
        "original_filename": original_filename,
    }
    input_path = _write_request_payload(job_id, payload)
    access_token = issue_job_access_token()

    job = HostedJob(
        id=job_id,
        input_type=input_type,
        email=email,
        access_token_hash=hash_job_access_token(access_token),
        status="queued",
        input_path=input_path,
        backend_mode=describe_execution_mode()["mode"],
        max_attempts=settings.max_job_attempts,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialize_job(job, access_token=access_token)


@router.get("", response_model=JobListResponse, dependencies=[Depends(require_admin_api_key)])
def list_jobs(db: Session = Depends(get_db)) -> JobListResponse:
    jobs = db.query(HostedJob).order_by(HostedJob.created_at.desc()).all()
    return JobListResponse(items=[_serialize_job(job) for job in jobs])


@router.get("/mode")
def get_mode() -> dict:
    return describe_execution_mode()


@router.get("/hpc/diagnostics", dependencies=[Depends(require_admin_api_key)])
def get_hpc_diagnostics() -> dict:
    return run_hpc_diagnostics()


@router.get("/results/{job_id}")
def get_result(
    job_id: str,
    x_job_token: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    job = _get_job_with_access(db, job_id, x_job_token, x_api_key)
    if not job.result_path:
        raise HTTPException(status_code=404, detail=f"No result available for job: {job_id}")

    result_path = Path(job.result_path)
    if not result_path.exists():
        raise HTTPException(status_code=404, detail=f"Result file missing for job: {job_id}")
    return json.loads(result_path.read_text(encoding="utf-8"))


@router.get("/files/{job_id}/structure-image")
def get_structure_image(
    job_id: str,
    x_job_token: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    job = _get_job_with_access(db, job_id, x_job_token, x_api_key)
    settings = get_settings()
    image_path = settings.results_dir / f"{job.id}.structure.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"No structure image available for job: {job_id}")
    return FileResponse(path=str(image_path), media_type="image/png", filename=image_path.name)


@router.get("/files/{job_id}/alphafold")
def get_alphafold_structure(
    job_id: str,
    x_job_token: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    job = _get_job_with_access(db, job_id, x_job_token, x_api_key)
    settings = get_settings()
    predicted_path = settings.results_dir / f"{job.id}.alphafold.pdb"
    if not predicted_path.exists():
        raise HTTPException(status_code=404, detail=f"No AlphaFold structure available for job: {job_id}")
    return FileResponse(
        path=str(predicted_path),
        media_type="chemical/x-pdb",
        filename=predicted_path.name,
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    x_job_token: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> JobResponse:
    job = _get_job_with_access(db, job_id, x_job_token, x_api_key)
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
