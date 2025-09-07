from __future__ import annotations

import logging
import time
from typing import Any

_DOM_LOG = logging.getLogger("zyra.api.domain")
_MCP_LOG = logging.getLogger("zyra.api.mcp")


_SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "bearer",
}


def _redact(value: Any) -> Any:
    try:
        if isinstance(value, str):
            # naive redact for tokens in strings
            for k in _SENSITIVE_KEYS:
                if k in value.lower():
                    return "[REDACTED]"
            return value
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
