"""Small in-memory rate limiter for public submission endpoints."""

from __future__ import annotations

from collections import deque
from threading import Lock
import time

from fastapi import HTTPException, Request

from ..config import get_settings


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._buckets: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please retry later.",
                )
            bucket.append(now)


rate_limiter = SlidingWindowRateLimiter()


def enforce_create_job_rate_limit(request: Request) -> None:
    settings = get_settings()
    client_host = request.client.host if request.client else "unknown"
    route_key = f"{request.method}:{request.url.path}:{client_host}"
    rate_limiter.check(
        key=route_key,
        limit=settings.rate_limit_create_job_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
