# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from zyra.api.models.domain_api import DomainRunResponse
from zyra.api.models.types import ErrorInfo


def _sanitize(obj: Any) -> Any:
    """Make objects JSON-serializable by converting exceptions to strings.

    Recursively processes dicts/lists/tuples, leaves primitives as-is, and
    stringifies unknown objects.
    """
    try:
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            t = type(obj)
            return t(_sanitize(v) for v in obj)
        if isinstance(obj, BaseException):
            return str(obj)
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return str(obj)
    except Exception:
        return str(obj)


def domain_error_response(
    *,
    status_code: int,
    err_type: str,
    message: str,
    details: dict[str, Any] | None = None,
    retriable: bool | None = None,
) -> JSONResponse:
    body = DomainRunResponse(
        status="error",
        error=ErrorInfo(
            type=err_type,
            message=message,
            details=_sanitize(details) if details is not None else None,
            retriable=retriable,
        ),
    ).model_dump()
    return JSONResponse(content=body, status_code=status_code)
