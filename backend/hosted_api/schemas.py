"""Pydantic models for the hosted async-product scaffold."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    input_type: Literal["structure", "sequence", "fasta"]
    email: str | None = None
    sequence: str | None = None
    sequence_id: str | None = None
    notes: str | None = None


class JobSummary(BaseModel):
    classification: str
    best_match_id: str | None = None
    tm_score: float | None = None
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
    input_path: str
    result_path: str | None = None
    summary: dict[str, Any] | None = None
    error_message: str | None = None
    backend_mode: str


class JobListResponse(BaseModel):
    items: list[JobResponse]
