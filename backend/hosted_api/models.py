"""Persistent job metadata for the hosted product scaffold."""

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HostedJob(Base):
    __tablename__ = "hosted_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    input_type: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_run_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_result_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_stdout_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_stderr_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend_mode: Mapped[str] = mapped_column(Text, nullable=False, default="local")
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=2)
