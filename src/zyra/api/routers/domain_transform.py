# SPDX-License-Identifier: Apache-2.0
"""Domain API: Transform.

Exposes ``POST /transform`` for lightweight transforms and metadata helpers.
Includes optional request body-size limits (``ZYRA_DOMAIN_MAX_BODY_BYTES``) and
structured logging of calls/durations.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import ValidationError

from zyra.api.models.cli_request import CLIRunRequest
from zyra.api.models.domain_api import DomainRunRequest, DomainRunResponse
from zyra.api.routers.cli import get_cli_matrix, run_cli_endpoint
from zyra.api.schemas.domain_args import normalize_and_validate
from zyra.api.utils.errors import domain_error_response
from zyra.api.utils.obs import log_domain_call
from zyra.utils.env import env_int

router = APIRouter(tags=["transform"], prefix="")


@router.post("/transform", response_model=DomainRunResponse)
def transform_run(
    req: DomainRunRequest, bg: BackgroundTasks, request: Request
) -> DomainRunResponse:
    """Run a transform-domain tool and return a standardized response.

    Note: The transform group has been merged under ``process``. This endpoint
    remains for backward compatibility, but new flows should prefer
    ``/v1/process`` with the same tools.
    """
    # Log a gentle deprecation warning
    try:
        import logging as _log

        _log.getLogger("zyra.api.domain").warning(
            "[deprecated] '/transform' is merged under '/process'; prefer '/v1/process'"
        )
    except Exception:
        pass
    try:
        max_bytes = int(env_int("DOMAIN_MAX_BODY_BYTES", 0))
    except Exception:
        max_bytes = 0
    if max_bytes:
        try:
            cl = int(request.headers.get("content-length") or 0)
        except Exception:
            cl = 0
        if cl and cl > max_bytes:
            return domain_error_response(
                status_code=413,
                err_type="request_too_large",
                message=f"Request too large: {cl} bytes (limit {max_bytes})",
                details={"content_length": cl, "limit": max_bytes},
            )
    matrix = get_cli_matrix()
    stage = "transform"
    allowed = set(matrix.get(stage, {}).get("commands", []) or [])
    if req.tool not in allowed:
        return domain_error_response(
            status_code=400,
            err_type="invalid_tool",
            message="Invalid tool for transform domain",
            details={"allowed": sorted(list(allowed))},
        )

    mode = (req.options.mode if req.options else None) or "sync"
    try:
        args = normalize_and_validate(stage, req.tool, req.args)
    except ValidationError as ve:
        return domain_error_response(
            status_code=400,
            err_type="validation_error",
            message="Invalid arguments",
            details={"errors": ve.errors()},
        )
    import time as _time

    _t0 = _time.time()
    resp = run_cli_endpoint(
        CLIRunRequest(stage=stage, command=req.tool, args=args, mode=mode), bg
    )
    if getattr(resp, "job_id", None):
        return DomainRunResponse(
            status="accepted",
            job_id=resp.job_id,
            poll=f"/jobs/{resp.job_id}",
            download=f"/jobs/{resp.job_id}/download",
            manifest=f"/jobs/{resp.job_id}/manifest",
        )
    res = DomainRunResponse(
        status="ok" if (resp.exit_code or 1) == 0 else "error",
        stdout=getattr(resp, "stdout", None),
        stderr=getattr(resp, "stderr", None),
        exit_code=getattr(resp, "exit_code", None),
    )
    from contextlib import suppress

    with suppress(Exception):
        log_domain_call(
            stage,
            req.tool,
            args,
            getattr(resp, "job_id", None),
            getattr(resp, "exit_code", None),
            _t0,
        )
    return res
