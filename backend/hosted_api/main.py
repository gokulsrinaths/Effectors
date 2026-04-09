"""Hosted async-product scaffold entrypoint."""

from fastapi import FastAPI

from .config import get_settings
from .db import init_db
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


app.include_router(jobs_router)
