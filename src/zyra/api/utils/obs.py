# SPDX-License-Identifier: Apache-2.0
"""Observability helpers for API logging.

Provides structured logging functions with best-effort redaction of sensitive
fields and duration tracking for domain and MCP calls.

Loggers
- ``zyra.api.domain`` — domain endpoints
- ``zyra.api.mcp`` — MCP JSON-RPC methods
"""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from typing import Any

from zyra.utils.env import env_bool

_DOM_LOG = logging.getLogger("zyra.api.domain")
_MCP_LOG = logging.getLogger("zyra.api.mcp")


_SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "client_secret",
    "refresh_token",
    "private_key",
    "session_token",
    "secret",
    "bearer",
}

_SENSITIVE_TOKEN_RE = re.compile(
    r"(?i)\b(?:authorization|password|token|api[_-]?key|access[_-]?key|client[_-]?secret|refresh[_-]?token|private[_-]?key|session[_-]?token|secret|bearer)\b"
)

# Key-value style (e.g., "password=VALUE", "api_key: VALUE") — redact VALUE only
_KV_RE = re.compile(
    r"(?i)\b(authorization|password|token|api[_-]?key|access[_-]?key|client[_-]?secret|refresh[_-]?token|private[_-]?key|session[_-]?token|secret|bearer)\b\s*[:=]\s*([^\s&#;]+)"
)

# URL query parameters (e.g., "?api_key=VALUE" or "&token=VALUE") — redact VALUE only
_URL_PARAM_RE = re.compile(
    r"(?i)([?&])(authorization|password|token|api[_-]?key|access[_-]?key|client[_-]?secret|refresh[_-]?token|private[_-]?key|session[_-]?token|secret|bearer)=([^&#]+)"
)


@lru_cache(maxsize=1)
def _redact_strict() -> bool:
    """Cached strict-mode flag to avoid repeated env lookups.

    Set via environment variable `ZYRA_REDACT_STRICT` (truthy values: 1/true/yes).
    """
    try:
        # Use the documented, namespaced variable for consistency with repo
        # conventions (ZYRA_*).
        return env_bool("ZYRA_REDACT_STRICT", False)
    except Exception:
        return False


def _redact(value: Any) -> Any:
    try:
        if isinstance(value, str):
            # Step 1: redact values in key-value or URL parameter forms while
            # preserving the surrounding structure for debuggability.
            def _kv_sub(m: re.Match[str]) -> str:
                return (
                    f"{m.group(1)}=[REDACTED]"
                    if m.group(0).find("=") != -1
                    else f"{m.group(1)}: [REDACTED]"
                )

            s = _KV_RE.sub(lambda m: _kv_sub(m), value)
            s = _URL_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}=[REDACTED]", s)

            # Step 2: redact entire string only when:
            #  - safe mode: a sensitive token appears as a whole word; or
            #  - strict mode: a sensitive token substring appears anywhere.
            strict = _redact_strict()
            has_token = _SENSITIVE_TOKEN_RE.search(s) is not None
            has_substring = any(k in s.lower() for k in _SENSITIVE_KEYS)
            if has_token or (strict and has_substring):
                return "[REDACTED]"
            return s
        if isinstance(value, dict):
            return {
                k: ("[REDACTED]" if k.lower() in _SENSITIVE_KEYS else _redact(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_redact(v) for v in value]
        return value
    except Exception:
        return value


def log_domain_call(
    domain: str,
    tool: str,
    args: dict[str, Any],
    job_id: str | None,
    exit_code: int | None,
    started_at: float,
) -> None:
    """Log a domain endpoint invocation with basic fields.

    Records: domain, tool, redacted args, job_id, exit_code, and duration_ms.
    """
    try:
        dur_ms = int((time.time() - started_at) * 1000)
        payload = {
            "event": "domain_call",
            "domain": domain,
            "tool": tool,
            "job_id": job_id,
            "exit_code": exit_code,
            "duration_ms": dur_ms,
            "args": _redact(dict(args or {})),
        }
        _DOM_LOG.info("%s", payload)
    except Exception:
        # Avoid raising on logging failures
        pass


def log_mcp_call(
    method: str,
    params: dict[str, Any] | None,
    started_at: float,
    status: str | None = None,
    error_code: int | None = None,
) -> None:
    """Log an MCP RPC call with method, status, error_code, and duration_ms."""
    try:
        dur_ms = int((time.time() - started_at) * 1000)
        payload = {
            "event": "mcp_call",
            "method": method,
            "status": status,
            "error_code": error_code,
            "duration_ms": dur_ms,
            "params": _redact(dict(params or {})),
        }
        _MCP_LOG.info("%s", payload)
    except Exception:
        pass
