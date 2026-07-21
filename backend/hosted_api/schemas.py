"""Pydantic models for the hosted async-product scaffold."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class JobCreateRequest(BaseModel):
    job_id: str | None = None
    input_type: Literal["structure", "sequence", "fasta"]
    email: str | None = None
    sequence: str | None = None
    sequence_id: str | None = None
    run_alphafold: bool = False
    notes: str | None = None


class JobSummary(BaseModel):
    classification: str
    best_match_id: str | None = None
    # tm_score is the Chain 1 (query-normalized) score, kept for compatibility.
    tm_score: float | None = None
    tm_score_chain1: float | None = None
    tm_score_chain2: float | None = None
    tm_score_best: float | None = None
    alignment_type: str | None = None
    coverage_query: float | None = None
    coverage_target: float | None = None
    seq_id: float | None = None
    blast_hit_id: str | None = None
    message: str


class JobResponse(BaseModel):
    id: str
    input_type: str
    email: str | None
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: dict[str, Any] | None = None
    error_message: str | None = None
    backend_mode: str
    attempt_count: int
    max_attempts: int
    has_result: bool
    poll_path: str
    result_path: str | None = None
    access_token: str | None = None
    remote_job_id: str | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
