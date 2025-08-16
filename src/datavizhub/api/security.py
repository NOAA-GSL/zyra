from __future__ import annotations

import os
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
import secrets


API_KEY_ENV = "DATAVIZHUB_API_KEY"
API_KEY_HEADER_ENV = "DATAVIZHUB_API_KEY_HEADER"

HEADER_NAME = os.environ.get(API_KEY_HEADER_ENV, "X-API-Key")
api_key_header = APIKeyHeader(name=HEADER_NAME, auto_error=False)


async def require_api_key(api_key: str | None = Security(api_key_header)) -> bool:
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
    if isinstance(api_key, str) and isinstance(expected, str) and secrets.compare_digest(api_key, expected):
        return True
    raise HTTPException(status_code=401, detail="Unauthorized: invalid API key")
