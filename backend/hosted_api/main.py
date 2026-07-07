"""Hosted async-product scaffold entrypoint."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .services.execution import describe_execution_mode
from .routes.jobs import router as jobs_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
        "max_upload_bytes": settings.max_upload_bytes,
        "max_sequence_chars": settings.max_sequence_chars,
        "max_job_attempts": settings.max_job_attempts,
        "job_lease_seconds": settings.job_lease_seconds,
        "job_heartbeat_seconds": settings.job_heartbeat_seconds,
        "rate_limit_window_seconds": settings.rate_limit_window_seconds,
        "rate_limit_create_job_limit": settings.rate_limit_create_job_limit,
        "smtp_configured": bool(settings.smtp_host),
        "admin_api_key_configured": bool(settings.admin_api_key),
        "cors_allowed_origins": settings.cors_allowed_origins,
    }


app.include_router(jobs_router)
