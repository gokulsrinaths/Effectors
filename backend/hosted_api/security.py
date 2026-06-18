"""Lightweight security helpers for the hosted API."""

from __future__ import annotations

from hashlib import sha256
import secrets

from fastapi import Header, HTTPException

from .config import get_settings


def require_admin_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require an API key only when one is configured.

    This is intended for admin-style endpoints, not public submission endpoints.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin endpoints are disabled until an admin API key is configured.")
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key.")


def issue_job_access_token() -> str:
    return secrets.token_urlsafe(24)


def hash_job_access_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def is_admin_request(x_api_key: str | None) -> bool:
    settings = get_settings()
    return bool(settings.admin_api_key and x_api_key == settings.admin_api_key)
