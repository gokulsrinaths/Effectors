"""Database wiring for hosted job records."""

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings


settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


HOSTED_JOB_ADDITIVE_COLUMNS = {
    "access_token_hash": "TEXT NOT NULL DEFAULT ''",
    "reservation_expires_at": "DATETIME",
    "last_heartbeat_at": "DATETIME",
    "remote_job_id": "TEXT",
    "remote_run_dir": "TEXT",
    "remote_result_path": "TEXT",
    "remote_stdout_path": "TEXT",
    "remote_stderr_path": "TEXT",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401

    url = make_url(settings.database_url)
    if url.drivername.startswith("sqlite") and url.database:
        db_path = Path(url.database)
        if not db_path.is_absolute():
            db_path = (Path.cwd() / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    _run_additive_migrations()


def _run_additive_migrations() -> None:
    inspector = inspect(engine)
    if "hosted_jobs" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("hosted_jobs")}
    missing_columns = {
        name: ddl
        for name, ddl in HOSTED_JOB_ADDITIVE_COLUMNS.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, ddl in missing_columns.items():
            connection.execute(text(f"ALTER TABLE hosted_jobs ADD COLUMN {name} {ddl}"))
