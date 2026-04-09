"""Lightweight security helpers for the hosted API."""

from __future__ import annotations

from fastapi import Header, HTTPException

from .config import get_settings


def require_admin_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require an API key only when one is configured.

    This is intended for admin-style endpoints, not public submission endpoints.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        return
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key.")
