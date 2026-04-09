"""Hosted async-product scaffold entrypoint."""

from fastapi import FastAPI

from .config import get_settings
from .db import init_db
from .services.execution import describe_execution_mode
from .routes.jobs import router as jobs_router


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "ok",
        "mode": "hosted-scaffold",
    }


@app.get("/health")
def health() -> dict:
    return {
        "service": settings.app_name,
        "status": "ok",
        "execution": describe_execution_mode(),
        "uploads_dir": str(settings.uploads_dir),
        "results_dir": str(settings.results_dir),
        "logs_dir": str(settings.logs_dir),
        "max_upload_bytes": settings.max_upload_bytes,
        "max_sequence_chars": settings.max_sequence_chars,
        "max_job_attempts": settings.max_job_attempts,
        "smtp_configured": bool(settings.smtp_host),
        "admin_api_key_configured": bool(settings.admin_api_key),
    }


app.include_router(jobs_router)
