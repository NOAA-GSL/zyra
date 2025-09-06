from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from zyra.api.models.domain_api import DomainRunResponse
from zyra.api.models.types import ErrorInfo


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
            type=err_type, message=message, details=details, retriable=retriable
        ),
    ).model_dump()
    return JSONResponse(content=body, status_code=status_code)
