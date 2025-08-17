from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from threading import Lock

from fastapi import HTTPException, Request, Security
from fastapi.security.api_key import APIKeyHeader

API_KEY_ENV = "DATAVIZHUB_API_KEY"
API_KEY_HEADER_ENV = "DATAVIZHUB_API_KEY_HEADER"

HEADER_NAME = os.environ.get(API_KEY_HEADER_ENV, "X-API-Key")
api_key_header = APIKeyHeader(name=HEADER_NAME, auto_error=False)

# Simple in-memory throttle for failed auth attempts (per client IP)
_FAIL_LOG: dict[str, list[float]] = {}
_FAIL_LOCK: Lock = Lock()


def _auth_limits() -> tuple[int, int, float]:
    """Return (max_failures, window_seconds, delay_seconds) from env with defaults."""
    try:
        maxf = int(os.environ.get("DATAVIZHUB_AUTH_FAILS_PER_WINDOW", "10") or 10)
    except Exception:
        maxf = 10
    try:
        win = int(os.environ.get("DATAVIZHUB_AUTH_WINDOW_SECONDS", "60") or 60)
    except Exception:
        win = 60
    try:
        delay_ms = int(os.environ.get("DATAVIZHUB_AUTH_FAIL_DELAY_MS", "100") or 100)
    except Exception:
        delay_ms = 100
    return maxf, win, max(0.0, float(delay_ms) / 1000.0)


def _record_failure(client_ip: str) -> int:
    """Record a failed attempt for client_ip and return recent count within window."""
    maxf, win, _delay = _auth_limits()
    now = time.time()
    with _FAIL_LOCK:
        lst = _FAIL_LOG.get(client_ip) or []
        # Drop old entries
        lst = [t for t in lst if (now - t) <= win]
        lst.append(now)
        _FAIL_LOG[client_ip] = lst
        return len(lst)


def _should_throttle(count: int) -> bool:
    maxf, _win, _delay = _auth_limits()
    return count >= maxf


async def require_api_key(
    api_key: str | None = Security(api_key_header), request: Request = None
) -> bool:
    """Require an API key when `DATAVIZHUB_API_KEY` is set.

    Behavior
    - Reads the expected value from `DATAVIZHUB_API_KEY`.
    - If not set, authentication is disabled (returns True).
    - If set, compares against header value; raises 401 when missing/invalid.
    """
    expected = os.environ.get(API_KEY_ENV)
    if not expected:
        return True  # auth disabled
    # Only compare when both are strings; otherwise treat as invalid
    if (
        isinstance(api_key, str)
        and isinstance(expected, str)
        and secrets.compare_digest(api_key, expected)
    ):
        return True
    # Failed authentication: apply small delay and basic rate limit
    client_ip = None
    try:
        if request is not None:
            client = getattr(request, "client", None)
            client_ip = getattr(client, "host", None)
    except Exception:
        client_ip = None
    # Delay every failure slightly to slow brute force
    _maxf, _win, delay_sec = _auth_limits()
    if delay_sec > 0:
        try:
            await asyncio.sleep(delay_sec)
        except Exception:
            # Fall back to blocking sleep if event loop context is unavailable
            logging.warning(
                "Falling back to blocking time.sleep() in require_api_key; this may block the event loop."
            )
            time.sleep(delay_sec)
    # Count and possibly throttle
    if client_ip:
        cnt = _record_failure(client_ip)
        if _should_throttle(cnt):
            # Advise retry-after for the remaining window
            _maxf, win, _d = _auth_limits()
            headers = {"Retry-After": str(win)}
            raise HTTPException(
                status_code=429, detail="Too Many Attempts", headers=headers
            )
    raise HTTPException(status_code=401, detail="Unauthorized: invalid API key")
