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

router = APIRouter(tags=["visualize"], prefix="")


@router.post("/visualize", response_model=DomainRunResponse)
def visualize_run(
    req: DomainRunRequest, bg: BackgroundTasks, request: Request
) -> DomainRunResponse:
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
    stage = "visualize"
    allowed = set(matrix.get(stage, {}).get("commands", []) or [])
    if req.tool not in allowed:
        return domain_error_response(
            status_code=400,
            err_type="invalid_tool",
            message="Invalid tool for visualize domain",
            details={"allowed": sorted(list(allowed))},
        )

    if req.options and req.options.sync is not None:
        mode = "sync" if req.options.sync else "async"
    else:
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
    ok = resp.exit_code == 0
    res = DomainRunResponse(
        status="ok" if ok else "error",
        result={"argv": getattr(resp, "argv", None)},
        logs=[
            *(
                [{"stream": "stdout", "text": resp.stdout}]
                if getattr(resp, "stdout", None)
                else []
            ),
            *(
                [{"stream": "stderr", "text": resp.stderr}]
                if getattr(resp, "stderr", None)
                else []
            ),
        ],
        stdout=getattr(resp, "stdout", None),
        stderr=getattr(resp, "stderr", None),
        exit_code=getattr(resp, "exit_code", None),
        error=(
            {
                "type": "execution_error",
                "message": (resp.stderr or "Command failed"),
                "details": {"exit_code": resp.exit_code},
            }
            if not ok
            else None
        ),
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
